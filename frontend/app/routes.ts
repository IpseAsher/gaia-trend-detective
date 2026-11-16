import { index, route, type RouteConfig } from "@react-router/dev/routes";

export default [index("routes/home.tsx"), route("explore", "routes/explore.tsx")] satisfies RouteConfig;
