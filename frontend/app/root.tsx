import type { ReactNode } from "react";
import {
  isRouteErrorResponse,
  Links,
  Link,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useRouteError,
} from "react-router";

import "./styles.css";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <meta
          name="description"
          content="Investigate regional precipitation trends across months, seasons, and years with GAIA."
        />
        <title>GAIA — Earth System Trend Detective</title>
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export function HydrateFallback() {
  return (
    <main className="page-shell loading-screen">
      <p className="wordmark">GAIA</p>
      <h1>Earth System Trend Detective</h1>
      <p role="status">Loading GAIA…</p>
      <noscript>Enable JavaScript to check data availability and use GAIA.</noscript>
    </main>
  );
}

export function ErrorBoundary() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;

  return (
    <main className="page-shell loading-screen">
      <p className="wordmark">GAIA</p>
      <h1>{notFound ? "Page not found" : "This page could not be loaded"}</h1>
      <p>
        {notFound
          ? "The page you requested does not exist."
          : "Please return to the home page and try again."}
      </p>
      <Link className="text-link" to="/">Return to GAIA</Link>
    </main>
  );
}

export default function App() {
  return <Outlet />;
}
