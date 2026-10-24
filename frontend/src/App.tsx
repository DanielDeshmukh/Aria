import CallApp from "./call/CallApp";
import CallPanel from "./call/CallPanel";
import Footer from "./components/Footer";
import Hero from "./components/Hero";
import Nav from "./components/Nav";
import Pipeline from "./components/Pipeline";
import { Section, SectionHead } from "./components/ui";
import { useRouteScroll } from "./routes";

export default function App() {
  if (window.location.pathname === "/call") return <CallApp />;
  useRouteScroll();
  return (
    <div className="relative isolate min-h-screen bg-paper font-sans text-ink">
      {/* backmost dotted grid */}
      <div className="bg-dotgrid pointer-events-none absolute inset-0 -z-10" aria-hidden />

      {/* paper grain overlay */}
      <div className="bg-noise pointer-events-none fixed inset-0 z-[70] opacity-[0.05] mix-blend-multiply" aria-hidden />

      <Nav />
      <main>
        <Hero />

        {/* live call — the product, embedded */}
        <Section id="call" className="border-t border-line bg-card/40 py-16 md:py-24">
          <SectionHead
            no="01"
            kicker="live — talk to Aria"
            title={
              <>
                Try it <span className="italic text-pine">right here</span>
              </>
            }
            desc="The full call screen, embedded in this page. Allow the microphone, hit Start Call and ask about ORD-101 — the same pipeline that ships to the live URL runs in this tab."
          />
          <div className="rounded-2xl hairline bg-card p-5 shadow-[0_2px_10px_-6px_rgba(19,32,25,0.12)] md:p-7">
            <CallPanel />
          </div>
        </Section>

        <div className="border-t border-line">
          <Pipeline />
        </div>
      </main>
      <Footer />
    </div>
  );
}
