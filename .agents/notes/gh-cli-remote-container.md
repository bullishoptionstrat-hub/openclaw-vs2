# Installing the GitHub CLI in a remote container

Notes from setting up `gh` inside a Claude Code remote execution container
(Ubuntu 24.04, x86_64) that sits behind the agent HTTPS proxy.

The short version: `gh` can be built and installed successfully, but it cannot
reach this repository's GitHub API. Use the GitHub MCP tools for GitHub work.

## Why not apt or a release download

- `apt-get install gh` works, but the Ubuntu 24.04 candidate is `2.45.0`,
  which is far behind upstream.
- Downloading an official release tarball does not work. Requests to
  `api.github.com` return `HTTP 403` through the agent proxy, so release
  lookup and asset download both fail.

## Build from source instead

`git clone` of public repos is allowed through the proxy, and Go module
downloads go direct because `proxy.golang.org` is listed in `no_proxy`.
That makes a source build the most reliable path:

```sh
git clone https://github.com/cli/cli.git
cd cli
go build -trimpath -o bin/gh ./cmd/gh
install -m 0755 bin/gh /usr/local/bin/gh
```

This produced a working `gh` from tag `v2.98.0`. Build time is a couple of
minutes, mostly Go module downloads. The resulting binary is around 55 MB.

## What actually works

Generic, unauthenticated-style endpoints relay fine:

```sh
gh api rate_limit   # returns real data
```

Authenticated access to repositories does not:

- `gh repo view <owner>/<repo>` fails with `HTTP 403`. GraphQL is disabled
  through the proxy except for a pinned set of pull request review operations.
- `gh api repos/<owner>/<repo>` (the REST fallback the proxy itself suggests)
  also fails with `HTTP 403` and the message that GitHub access is not enabled
  for the session, and that an org admin must connect the Claude GitHub App.
- `gh auth status` reports the token as invalid. `GH_TOKEN` in the container is
  a placeholder string, not a credential; the proxy substitutes real
  credentials only on requests it relays.

So `gh pr`, `gh issue`, and `gh repo` are not usable here. Enabling them is an
org admin action outside the container.

## Practical guidance

- For GitHub operations in a remote container, use the GitHub MCP tools. They
  are the sanctioned path and they have the access `gh` lacks.
- Reach for a source build only when you need the `gh` binary itself, for
  example to read its behavior or test against it locally.
- Remote containers are ephemeral. Anything installed this way disappears when
  the session ends, so treat it as scratch rather than setup worth preserving.
