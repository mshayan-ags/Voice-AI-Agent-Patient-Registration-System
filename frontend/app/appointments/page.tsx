"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listAppointments, type Appointment } from "@/lib/api";

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAppointments().then(setAppointments).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="container">
      <div className="header">
        <div>
          <h1>Appointments</h1>
          <p>Mock scheduling booked through the voice agent or the API — demonstrates the pattern, not a real scheduling system.</p>
        </div>
        <span className="badge">{appointments?.length ?? 0} booked</span>
      </div>

      <div className="card">
        {error && <div className="empty">Error: {error}</div>}
        {!error && appointments === null && <div className="empty">Loading…</div>}
        {!error && appointments?.length === 0 && (
          <div className="empty">No appointments booked yet.</div>
        )}
        {!error && appointments && appointments.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Patient</th>
                <th>When</th>
                <th>Reason</th>
                <th>Status</th>
                <th>Booked</th>
              </tr>
            </thead>
            <tbody>
              {appointments.map((a) => (
                <tr key={a.appointment_id}>
                  <td>
                    {a.patient_name ? (
                      <Link href={`/patients/${a.patient_id}`}>{a.patient_name}</Link>
                    ) : (
                      <span className="field-label" style={{ display: "inline" }}>
                        unknown patient
                      </span>
                    )}
                  </td>
                  <td>{a.label}</td>
                  <td>{a.reason || "—"}</td>
                  <td>
                    <span className="badge good">{a.status}</span>
                  </td>
                  <td>{new Date(a.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
