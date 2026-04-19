"""
ALERT ENGINE - TIERED ALERT SYSTEM

Multi-channel alert delivery with intelligent prioritization.

Alert Tiers (prevent over-alerting):
- Tier 1 (Low): score 5-6, confidence > 0.6 → UI only (dashboard)
- Tier 2 (Actionable): score 7-8, confidence > 0.7 → Discord + push notification
- Tier 3 (High conviction): score 9+, confidence > 0.85 → ALL channels + highlight + mobile

Channels:
- UI/Dashboard: All tiers
- Discord: Tier 2+
- Email (SMTP): Tier 3 only
- Push notification: Tier 2+
- SMS: Tier 3 only (premium)

Architecture:
- Alert rules (configurable filters)
- Alert formatter (Discord embeds, email HTML, push text)
- Channel router (which channel for which tier)
- Alert history (audit trail)

NOT JUST NOTIFICATIONS:
- Alerts are automated decision triggers
- They should reduce screen time and improve discipline
- Each alert includes full trade context for quick action
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class AlertTier(Enum):
    """Alert priority tier."""

    TIER_1 = "tier_1"  # Low: UI only
    TIER_2 = "tier_2"  # Actionable: Discord + push
    TIER_3 = "tier_3"  # High: All channels


class AlertType(Enum):
    """Alert event type."""

    TRADE_CREATED = "trade_created"
    HIGH_CONFIDENCE_SETUP = "high_confidence_setup"
    TRADE_EXECUTED = "trade_executed"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    TRADE_CLOSED = "trade_closed"
    MACRO_REGIME_CHANGE = "macro_regime_change"
    PERFORMANCE_MILESTONE = "performance_milestone"


@dataclass
class AlertRule:
    """Configurable alert rule."""

    enabled: bool = True
    minimum_confidence: float = 0.60  # Trade confidence minimum
    minimum_macro_confidence: float = 0.50  # Macro confidence minimum
    assets: List[str] = field(default_factory=list)  # Empty = all assets
    signal_types: List[str] = field(
        default_factory=list
    )  # Empty = all types
    exclude_regimes: List[str] = field(default_factory=list)  # Excluded regimes
    max_daily_alerts: int = 50  # Prevent spam


@dataclass
class Alert:
    """Single alert."""

    alert_id: str
    alert_type: AlertType
    alert_tier: AlertTier
    title: str
    body: str
    trade_id: Optional[str] = None
    confidence_score: float = 0.0
    macro_regime: str = "NEUTRAL"
    channels: List[str] = field(default_factory=list)  # discord, email, push, sms
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    sent_at: Optional[str] = None
    read: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "type": self.alert_type.value,
            "tier": self.alert_tier.value,
            "title": self.title,
            "body": self.body,
            "trade_id": self.trade_id,
            "confidence": self.confidence_score,
            "macro_regime": self.macro_regime,
            "channels": self.channels,
            "created_at": self.created_at,
            "sent_at": self.sent_at,
            "read": self.read,
        }


@dataclass
class DiscordAlert:
    """Discord embed format."""

    title: str
    description: str
    color: int  # Hex color
    fields: List[Dict] = field(default_factory=list)
    footer: str = ""
    image_url: Optional[str] = None

    def to_embed(self) -> Dict:
        """Convert to Discord embed JSON."""
        return {
            "title": self.title,
            "description": self.description,
            "color": self.color,
            "fields": [
                {"name": f["name"], "value": f["value"], "inline": f.get("inline", True)}
                for f in self.fields
            ],
            "footer": {"text": self.footer} if self.footer else None,
            "image": {"url": self.image_url} if self.image_url else None,
        }


def determine_alert_tier(
    signal_confidence: float,
    macro_confidence: float,
    confluence_score: Optional[float],
    macro_regime: str,
) -> AlertTier:
    """
    Determine alert tier based on confidence metrics.

    Args:
        signal_confidence: AI signal confidence (0-1)
        macro_confidence: Macro regime confidence (0-1)
        confluence_score: Multi-signal confluence (1-10, optional)
        macro_regime: Current regime

    Returns:
        AlertTier (1, 2, or 3)
    """

    # Composite score (weighted average)
    composite_score = (
        signal_confidence * 0.4 + macro_confidence * 0.3
    )

    # Confluence bonus
    if confluence_score and confluence_score >= 8:
        composite_score = min(1.0, composite_score + 0.1)

    # Macro alignment bonus
    if macro_regime in ["STRONG_RISK_ON", "RISK_ON"]:
        composite_score = min(1.0, composite_score + 0.05)

    # Tier determination
    if composite_score >= 0.85:
        return AlertTier.TIER_3
    elif composite_score >= 0.70:
        return AlertTier.TIER_2
    else:
        return AlertTier.TIER_1


def get_channels_for_tier(alert_tier: AlertTier) -> List[str]:
    """Get notification channels based on tier."""
    channel_map = {
        AlertTier.TIER_1: ["dashboard"],  # UI only
        AlertTier.TIER_2: ["dashboard", "discord", "push"],  # Notable signals
        AlertTier.TIER_3: ["dashboard", "discord", "push", "email", "sms"],  # High conviction
    }
    return channel_map.get(alert_tier, ["dashboard"])


def format_discord_alert(
    alert_title: str,
    trade_payload: Dict,
    alert_tier: AlertTier,
    alert_type: AlertType,
) -> DiscordAlert:
    """
    Format trade alert for Discord embed.

    Args:
        alert_title: Main alert title
        trade_payload: Execution payload
        alert_tier: Alert tier
        alert_type: Alert event type

    Returns:
        DiscordAlert (Discord embed format)
    """

    # Color based on tier
    color_map = {
        AlertTier.TIER_1: 5814783,  # Grey (0x589AFF)
        AlertTier.TIER_2: 16776960,  # Yellow (0xFFFF00)
        AlertTier.TIER_3: 16711680,  # Red (0xFF0000)
    }

    # Tier emoji
    tier_emoji = {
        AlertTier.TIER_1: "ℹ️",
        AlertTier.TIER_2: "⚠️",
        AlertTier.TIER_3: "🚨",
    }

    color = color_map.get(alert_tier, 5814783)
    emoji = tier_emoji.get(alert_tier, "ℹ️")

    fields = [
        {
            "name": "Asset",
            "value": f"{trade_payload.get('asset', 'N/A')}",
            "inline": True,
        },
        {
            "name": "Direction",
            "value": f"{trade_payload.get('direction', 'N/A')}",
            "inline": True,
        },
        {
            "name": "Entry",
            "value": f"${trade_payload.get('entry', 'N/A'):.2f}",
            "inline": True,
        },
        {
            "name": "Stop Loss",
            "value": f"${trade_payload.get('stop_loss', 'N/A'):.2f}",
            "inline": True,
        },
        {
            "name": "Take Profit",
            "value": f"${trade_payload.get('take_profit_targets', [0])[0]:.2f}"
            if trade_payload.get("take_profit_targets")
            else "N/A",
            "inline": True,
        },
        {
            "name": "Risk/Reward",
            "value": f"{trade_payload.get('risk_reward_ratio', 0):.2f}",
            "inline": True,
        },
        {
            "name": "Size",
            "value": f"{trade_payload.get('position_size', 0):.2f} units",
            "inline": False,
        },
        {
            "name": "Signal Confidence",
            "value": f"{trade_payload.get('signal_confidence', 0)*100:.0f}%",
            "inline": True,
        },
        {
            "name": "Macro Regime",
            "value": f"{trade_payload.get('macro_regime', 'NEUTRAL')} "
            f"(score: {trade_payload.get('macro_score', 0):.1f})",
            "inline": True,
        },
        {
            "name": "Signal Type",
            "value": f"{trade_payload.get('signal_type', 'unknown')}",
            "inline": True,
        },
    ]

    if trade_payload.get("confluence_score"):
        fields.append(
            {
                "name": "Confluence",
                "value": f"{trade_payload.get('confluence_score')}/10",
                "inline": True,
            }
        )

    return DiscordAlert(
        title=f"{emoji} {alert_title}",
        description=f"__{trade_payload.get('asset', 'N/A')}__ • "
        f"{trade_payload.get('direction', 'N/A')}",
        color=color,
        fields=fields,
        footer=f"Trade ID: {trade_payload.get('trade_id', 'unknown')[:8]}… • "
        f"Tier: {alert_tier.value.upper()}",
    )


def format_push_notification(
    trade_payload: Dict,
    alert_title: str,
) -> Dict:
    """
    Format alert for push notification (mobile).

    Keep it SHORT - mobile screens are small.
    """
    return {
        "title": alert_title,
        "body": (
            f"{trade_payload.get('asset')} {trade_payload.get('direction')} "
            f"@ ${trade_payload.get('entry'):.2f}} | "
            f"RR: {trade_payload.get('risk_reward_ratio', 0):.1f}"
        ),
        "trade_id": trade_payload.get("trade_id"),
        "tag": f"{trade_payload.get('asset')}_{trade_payload.get('direction')}",
    }


def format_email_alert(
    trade_payload: Dict,
    alert_title: str,
    alert_tier: AlertTier,
) -> str:
    """
    Format alert as HTML email.

    Include full trade context for offline review.
    """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>{alert_title}</h2>
        <p><strong>Tier:</strong> {alert_tier.value.upper()}</p>
        
        <h3>Trade Details</h3>
        <table style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f0f0f0;">
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Asset</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">{trade_payload.get('asset', 'N/A')}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Direction</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">{trade_payload.get('direction', 'N/A')}</td>
            </tr>
            <tr style="background-color: #f0f0f0;">
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Entry</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">${trade_payload.get('entry', 'N/A'):.2f}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Stop Loss</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">${trade_payload.get('stop_loss', 'N/A'):.2f}</td>
            </tr>
            <tr style="background-color: #f0f0f0;">
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Take Profit</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">
                    ${trade_payload.get('take_profit_targets', [0])[0]:.2f}
                </td>
            </tr>
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Risk/Reward</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">{trade_payload.get('risk_reward_ratio', 0):.2f}</td>
            </tr>
            <tr style="background-color: #f0f0f0;">
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>Position Size</strong></td>
                <td style="border: 1px solid #ddd; padding: 8px;">{trade_payload.get('position_size', 0):.2f} units</td>
            </tr>
        </table>
        
        <h3>Macro Context</h3>
        <p>
            <strong>Regime:</strong> {trade_payload.get('macro_regime', 'NEUTRAL')}<br>
            <strong>Macro Score:</strong> {trade_payload.get('macro_score', 0):.2f}<br>
            <strong>Signal Confidence:</strong> {trade_payload.get('signal_confidence', 0)*100:.0f}%<br>
            <strong>Signal Type:</strong> {trade_payload.get('signal_type', 'unknown')}
        </p>
        
        <hr>
        <p style="font-size: 12px; color: #999;">
            Trade ID: {trade_payload.get('trade_id', 'unknown')}<br>
            Generated: {datetime.utcnow().isoformat()}
        </p>
    </body>
    </html>
    """
    return html


class AlertEngine:
    """
    Core alert engine.

    Manages alert generation, routing, and delivery.
    """

    def __init__(self):
        """Initialize alert engine."""
        self.alerts_history: list = []
        self.daily_alert_count: int = 0
        self.alert_rules: AlertRule = AlertRule()

    def create_alert(
        self,
        alert_type: AlertType,
        trade_payload: Dict,
        alert_title: str,
    ) -> Alert:
        """Create and tier an alert."""

        signal_conf = trade_payload.get("signal_confidence", 0.5)
        macro_conf = trade_payload.get("macro_confidence", 0.5)
        confluence = trade_payload.get("confluence_score")
        macro_regime = trade_payload.get("macro_regime", "NEUTRAL")

        # Determine tier
        tier = determine_alert_tier(signal_conf, macro_conf, confluence, macro_regime)

        # Get channels for this tier
        channels = get_channels_for_tier(tier)

        # Create alert
        alert = Alert(
            alert_id=f"ALR_{trade_payload.get('trade_id', 'unknown')[:8]}",
            alert_type=alert_type,
            alert_tier=tier,
            title=alert_title,
            body=f"{trade_payload.get('asset')} {trade_payload.get('direction')}",
            trade_id=trade_payload.get("trade_id"),
            confidence_score=signal_conf,
            macro_regime=macro_regime,
            channels=channels,
        )

        self.alerts_history.append(alert)
        self.daily_alert_count += 1

        logger.info(
            f"Alert created: {alert.title} | Tier: {tier.value} | "
            f"Channels: {', '.join(channels)}"
        )

        return alert

    def should_alert(self, trade_payload: Dict) -> bool:
        """Check if alert should be sent based on rules."""
        if not self.alert_rules.enabled:
            return False

        if trade_payload.get("signal_confidence", 0) < self.alert_rules.minimum_confidence:
            return False

        if (
            trade_payload.get("macro_confidence", 0)
            < self.alert_rules.minimum_macro_confidence
        ):
            return False

        if self.alert_rules.assets and trade_payload.get(
            "asset"
        ) not in self.alert_rules.assets:
            return False

        if self.alert_rules.signal_types and trade_payload.get(
            "signal_type"
        ) not in self.alert_rules.signal_types:
            return False

        if (
            trade_payload.get("macro_regime") in self.alert_rules.exclude_regimes
        ):
            return False

        if self.daily_alert_count > self.alert_rules.max_daily_alerts:
            logger.warning("Max daily alerts reached, suppressing alert")
            return False

        return True

    def get_alert_formats(
        self, alert: Alert, trade_payload: Dict
    ) -> Dict[str, any]:
        """Get formatted alert for all channels."""
        return {
            "discord": format_discord_alert(
                alert.title,
                trade_payload,
                alert.alert_tier,
                alert.alert_type,
            ).to_embed() if "discord" in alert.channels else None,
            "push": format_push_notification(trade_payload, alert.title)
            if "push" in alert.channels
            else None,
            "email": format_email_alert(
                trade_payload, alert.title, alert.alert_tier
            )
            if "email" in alert.channels
            else None,
        }

    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Get recent alerts for dashboard."""
        return [alert.to_dict() for alert in self.alerts_history[-limit:]]
