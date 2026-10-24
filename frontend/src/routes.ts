import { useEffect } from "react";
import { NAV } from "./data/site";

const ROUTE_PATHS = new Set(["/", ...NAV.map((n) => `/${n.id}`)]);

const normalize = (path: string) => path.replace(/\/+$/, "") || "/";

/** Clean path ("/pipeline") → section id ("pipeline"); "/" and unknown → null (home). */
export function pathToSectionId(pathname: string): string | null {
  const clean = normalize(pathname);
  if (clean === "/") return null;
  const id = clean.slice(1);
  return NAV.some((n) => n.id === id) ? id : null;
}

/**
 * Same-page clean routing: nav links use /pipeline instead of /#pipeline,
 * hash targets like #call scroll in place, and the site stays one
 * continuous scroll. Handles click interception, history push,
 * back/forward, and deep-link scroll on load.
 */
export function useRouteScroll() {
  useEffect(() => {
    const scrollToPath = (instant: boolean, hash?: string) => {
      const behavior: ScrollBehavior = instant ? "instant" : "smooth";
      // explicit hash target (#call) wins; otherwise resolve the path's section
      const hashId = hash && hash.length > 1 ? hash.slice(1) : null;
      const id = hashId ?? pathToSectionId(window.location.pathname);
      const el = id ? document.getElementById(id) : null;
      if (el) el.scrollIntoView({ behavior, block: "start" });
      else window.scrollTo({ top: 0, behavior });
    };

    // legacy bookmarks like /#lens → clean /lens; /#call keeps its hash
    if (window.location.hash) {
      const id = window.location.hash.slice(1);
      const known = NAV.some((n) => n.id === id);
      history.replaceState({}, "", known ? `/${id}` : `/${""}${window.location.hash}`);
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
      if (!interacted) scrollToPath(true, window.location.hash);
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
        history.pushState({}, "", normalize(url.pathname) + (url.hash || ""));
      }
      scrollToPath(false, url.hash);
    };

    const onPopState = () => scrollToPath(false, window.location.hash);

    document.addEventListener("click", onClick);
    window.addEventListener("popstate", onPopState);
    return () => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("popstate", onPopState);
      INTERACT.forEach((t) => window.removeEventListener(t, markInteracted));
    };
  }, []);
}
