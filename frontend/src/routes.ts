import { useEffect } from "react";
import { NAV } from "./data/site";

const normalize = (path: string) => path.replace(/\/+$/, "") || "/";

/** Standalone views — native navigation only, never intercepted. */
const VIEW_ROUTES = new Set(["/call"]);

/** Landing sections addressable as clean paths (same-page smooth scroll). */
const SCROLL_PATHS = new Set(["/", ...NAV.map((n) => `/${n.id}`)]);

/** Clean path ("/pipeline") → section id ("pipeline"); "/" and unknown → null (home). */
export function pathToSectionId(pathname: string): string | null {
  const clean = normalize(pathname);
  if (clean === "/") return null;
  const id = clean.slice(1);
  return NAV.some((n) => n.id === id) ? id : null;
}

/**
 * Clean-path routing: every section lives at a plain path (/call, /pipeline),
 * clicking one pushes the URL and scrolls in place (one continuous scroll);
 * view routes like /call navigate natively. Handles click interception,
 * history push, back/forward, and deep-link scroll on load. No hash URLs.
 */
export function useRouteScroll() {
  useEffect(() => {
    const scrollToPath = (instant: boolean) => {
      const behavior: ScrollBehavior = instant ? "instant" : "smooth";
      const id = pathToSectionId(window.location.pathname);
      const el = id ? document.getElementById(id) : null;
      if (el) el.scrollIntoView({ behavior, block: "start" });
      else window.scrollTo({ top: 0, behavior });
    };

    // legacy bookmarks: /#call → native /call; /#pipeline → clean /pipeline
    if (window.location.hash) {
      const id = window.location.hash.slice(1);
      const known = NAV.some((n) => n.id === id);
      if (known && VIEW_ROUTES.has(`/${id}`)) {
        window.location.replace(`/${id}`);
        return;
      }
      history.replaceState({}, "", known ? `/${id}` : `/${window.location.hash}`);
    }

    // deep link: jump straight to the section once layout settles
    // (re-jumps after load/font swap, but never yanks a user who already moved)
    let interacted = false;
    const markInteracted = () => {
      interacted = true;
    };
    const INTERACT = ["wheel", "touchmove", "keydown", "pointerdown"] as const;
    INTERACT.forEach((t) => window.addEventListener(t, markInteracted, { passive: true }));

    const jump = () => {
      if (!interacted) scrollToPath(true);
    };
    requestAnimationFrame(() => requestAnimationFrame(jump));
    window.addEventListener("load", jump, { once: true });
    document.fonts?.ready.then(jump);

    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const anchor = (e.target as HTMLElement | null)?.closest?.("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href) return;
      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      const path = normalize(url.pathname);
      if (VIEW_ROUTES.has(path)) return; // standalone view: let the browser navigate
      if (!SCROLL_PATHS.has(path)) return;
      e.preventDefault();
      if (path !== normalize(window.location.pathname)) {
        history.pushState({}, "", path);
      }
      scrollToPath(false);
    };

    const onPopState = () => scrollToPath(false);

    document.addEventListener("click", onClick);
    window.addEventListener("popstate", onPopState);
    return () => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("popstate", onPopState);
      INTERACT.forEach((t) => window.removeEventListener(t, markInteracted));
    };
  }, []);
}
