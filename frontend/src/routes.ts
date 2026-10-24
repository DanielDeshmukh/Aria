import { useEffect } from "react";
import { NAV } from "./data/site";

const ROUTE_PATHS = new Set(["/", ...NAV.map((n) => `/${n.id}`)]);

const normalize = (path: string) => path.replace(/\/+$/, "") || "/";

/** Clean path ("/lens") → section id ("lens"); "/" and unknown → null (home). */
export function pathToSectionId(pathname: string): string | null {
  const clean = normalize(pathname);
  if (clean === "/") return null;
  const id = clean.slice(1);
  return NAV.some((n) => n.id === id) ? id : null;
}

/**
 * Same-page clean routing: nav links use /lens, /requirements … instead of
 * /#lens, while the site stays one continuous scroll. Handles click
 * interception, history push, back/forward, and deep-link scroll on load.
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

    // legacy bookmarks like /#lens → clean /lens
    if (window.location.hash) {
      const id = window.location.hash.slice(1);
      const path = NAV.some((n) => n.id === id) ? `/${id}` : "/";
      history.replaceState({}, "", path);
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
      if (!ROUTE_PATHS.has(normalize(url.pathname))) return;
      e.preventDefault();
      if (normalize(url.pathname) !== normalize(window.location.pathname)) {
        history.pushState({}, "", normalize(url.pathname));
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
