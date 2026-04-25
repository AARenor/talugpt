"use client";

import dynamic from "next/dynamic";

const FarmMap = dynamic(() => import("@/components/FarmMap"), {
  ssr: false,
  loading: () => (
    <div style={{ padding: 20, fontFamily: "system-ui" }}>Laen kaarti…</div>
  ),
});

const ChatWidget = dynamic(() => import("@/components/ChatWidget"), {
  ssr: false,
});

export default function Page() {
  return (
    <>
      <FarmMap />
      <ChatWidget />
    </>
  );
}
