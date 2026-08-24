"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listCallLogs, type CallLog } from "@/lib/api";

function ReasonBadge({ reason }: { reason?: string | null }) {
  if (!reason) return null;
  const isClean = reason === "assistant-ended-call" || reason === "customer-ended-call";
  return <span className={`badge${isClean ? "" : " bad"}`}>{reason}</span>;
}

function SuccessBadge({ value }: { value?: string | boolean | null }) {
  if (value === null || value === undefined || value === "") return null;
  const passed = value === true || value === "true";
  return <span className={`badge ${passed ? "good" : "bad"}`}>{passed ? "Succeeded" : "Failed"}</span>;
}

export default function CallsPage() {
  const [logs, setLogs] = useState<CallLog[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    listCallLogs().then(setLogs).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="container">
      <div className="header">
        <div>
          <h1>Call Logs</h1>
          <p>Every call Vapi has reported, including ones that never reached a patient record.</p>
        </div>
      </div>

      <div className="card">
        {error && <div className="empty">Error: {error}</div>}
        {!error && logs === null && <div className="empty">Loading…</div>}
        {!error && logs?.length === 0 && <div className="empty">No calls logged yet.</div>}
        {!error &&
          logs?.map((log) => {
            const sd = log.structured_data;
            return (
              <div
                key={log.call_id}
                style={{ borderBottom: "1px solid var(--border)", padding: "14px 0" }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    cursor: "pointer",
                    gap: 12,
                  }}
                  onClick={() => setExpanded(expanded === log.call_id ? null : log.call_id)}
                >
                  <div style={{ flex: 1 }}>
                    <div className="field-value">
                      {new Date(log.created_at).toLocaleString()}{" "}
                      {log.patient_id ? (
                        <Link
                          href={`/patients/${log.patient_id}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          (view patient)
                        </Link>
                      ) : (
                        <span className="field-label" style={{ display: "inline" }}>
                          (no patient linked)
                        </span>
                      )}
                    </div>
                    <div className="field-label" style={{ marginTop: 4, textTransform: "none" }}>
                      {log.summary ||
                        "No summary — call ended before a summary could be generated."}
                    </div>
                    {sd && (
                      <div className="chip-row">
                        {sd.caller_intent && <span className="chip">{sd.caller_intent}</span>}
                        {sd.registration_completed && <span className="chip">registered</span>}
                        {sd.existing_patient_recognized && (
                          <span className="chip">returning caller</span>
                        )}
                        {sd.appointment_booked && <span className="chip">appointment booked</span>}
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                    <SuccessBadge value={log.success_evaluation} />
                    <ReasonBadge reason={log.ended_reason} />
                  </div>
                </div>
                {expanded === log.call_id && (
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: 13,
                      marginTop: 10,
                      color: "var(--muted)",
                      maxHeight: 300,
                      overflowY: "auto",
                    }}
                  >
                    {(log.transcript as string) || "No transcript available."}
                  </pre>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
