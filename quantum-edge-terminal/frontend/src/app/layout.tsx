import React from 'react';
import './globals.css';

export const metadata = {
  title: 'Quantum Edge Terminal',
  description: 'Institutional-grade trading platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-qt-darker text-white font-mono">
        {children}
      </body>
    </html>
  );
}
