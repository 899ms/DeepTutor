"use client";

import dynamic from "next/dynamic";
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type {
  SessionViewerPanelHandle,
  SessionViewerPanelProps,
} from "./SessionViewerPanel";

export type { SessionViewerPanelHandle } from "./SessionViewerPanel";

// The viewer's activity, follow-up, and consultation UI is only needed once
// the panel opens or an event requests a tab.
const LoadedSessionViewerPanel = dynamic(
  () => import("./SessionViewerPanel"),
  { ssr: false },
);

type QueuedCall = {
  sessionId: string | null;
  run: (panel: SessionViewerPanelHandle) => void;
};

const LazySessionViewerPanel = forwardRef<
  SessionViewerPanelHandle,
  SessionViewerPanelProps
>(function LazySessionViewerPanel(props, ref) {
  const panelRef = useRef<SessionViewerPanelHandle | null>(null);
  const queuedCalls = useRef<QueuedCall[]>([]);
  const [loadRequested, setLoadRequested] = useState(props.open);

  const callPanel = useCallback(
    (run: QueuedCall["run"]) => {
      if (panelRef.current) {
        run(panelRef.current);
      } else {
        queuedCalls.current.push({ sessionId: props.sessionId, run });
        setLoadRequested(true);
      }
    },
    [props.sessionId],
  );

  // Chat events and attachment clicks can arrive while the panel chunk is
  // loading. Replay them in order once its imperative ref becomes available.
  const setPanelRef = useCallback(
    (panel: SessionViewerPanelHandle | null) => {
      panelRef.current = panel;
      if (!panel) return;
      const calls = queuedCalls.current;
      queuedCalls.current = [];
      for (const call of calls) {
        if (call.sessionId === props.sessionId) call.run(panel);
      }
    },
    [props.sessionId],
  );

  useImperativeHandle(
    ref,
    () => ({
      openFileTab: (attachment) =>
        callPanel((panel) => panel.openFileTab(attachment)),
      openWebTab: (url) => callPanel((panel) => panel.openWebTab(url)),
      openMarkdownNoteTab: () =>
        callPanel((panel) => panel.openMarkdownNoteTab()),
      openQuizFollowupTab: (context) =>
        callPanel((panel) => panel.openQuizFollowupTab(context)),
      openSelectionTutorTab: (selection, language) =>
        callPanel((panel) => panel.openSelectionTutorTab(selection, language)),
      openGeogebraTab: (payload) =>
        callPanel((panel) => panel.openGeogebraTab(payload)),
      openSubagentTab: (callId, label, events, focus) =>
        callPanel((panel) => panel.openSubagentTab(callId, label, events, focus)),
      focusActivityHome: () => callPanel((panel) => panel.focusActivityHome()),
    }),
    [callPanel],
  );

  return loadRequested || props.open ? (
    <LoadedSessionViewerPanel {...props} ref={setPanelRef} />
  ) : null;
});

export default LazySessionViewerPanel;
