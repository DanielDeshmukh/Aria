import Appendix from "./components/Appendix";
import Architecture from "./components/Architecture";
import CallApp from "./call/CallApp";
import Evaluating from "./components/Evaluating";
import Footer from "./components/Footer";
import Hero from "./components/Hero";
import Nav from "./components/Nav";
import Policies from "./components/Policies";
import Requirements from "./components/Requirements";
import Schedule from "./components/Schedule";
import Submission from "./components/Submission";
import TestScript from "./components/TestScript";
import ToolsBehavior from "./components/ToolsBehavior";
import { useRouteScroll } from "./routes";

export default function App() {
  if (window.location.pathname === "/call") return <CallApp />;
  useRouteScroll();
  return (
    <div className="relative isolate min-h-screen bg-paper font-sans text-ink">
      {/* backmost dotted grid */}
      <div className="bg-dotgrid pointer-events-none absolute inset-0 -z-10" aria-hidden />

      {/* paper grain overlay */}
      <div className="bg-noise pointer-events-none fixed inset-0 z-[70] opacity-[0.05] mix-blend-multiply" />

      <Nav />
      <main>
        <Hero />
        <Evaluating />
        <div className="border-t border-line"><Requirements /></div>
        <div className="border-t border-line"><Policies /></div>
        <div className="border-t border-line"><Architecture /></div>
        <ToolsBehavior />
        <div className="border-t border-line"><TestScript /></div>
        <Schedule />
        <Submission />
        <Appendix />
      </main>
      <Footer />
    </div>
  );
}
