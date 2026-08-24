"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getPatient,
  listAppointments,
  listCallLogs,
  type Appointment,
  type CallLog,
  type Patient,
} from "@/lib/api";

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className="field-value">{value}</div>
    </div>
  );
}

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPatient(id).then(setPatient).catch((e) => setError(e.message));
    listCallLogs(id).then(setLogs).catch(() => setLogs([]));
    listAppointments(id).then(setAppointments).catch(() => setAppointments([]));
  }, [id]);

  if (error) return <div className="container empty">Error: {error}</div>;
  if (!patient) return <div className="container empty">Loading…</div>;

  return (
    <div className="container">
      <Link href="/">&larr; All patients</Link>
      <div className="header" style={{ marginTop: 12 }}>
        <div>
          <h1>
            {patient.first_name} {patient.last_name}
          </h1>
        </div>
      </div>

      <div className="card">
        <div className="field-grid">
          <Field label="Date of birth" value={patient.date_of_birth} />
          <Field label="Sex" value={patient.sex} />
          <Field label="Phone" value={patient.phone_number} />
          <Field label="Email" value={patient.email} />
          <Field
            label="Address"
            value={`${patient.address_line_1}${patient.address_line_2 ? ", " + patient.address_line_2 : ""}, ${patient.city}, ${patient.state} ${patient.zip_code}`}
          />
          <Field label="Insurance" value={patient.insurance_provider} />
          <Field label="Member ID" value={patient.insurance_member_id} />
          <Field label="Preferred language" value={patient.preferred_language} />
          <Field label="Emergency contact" value={patient.emergency_contact_name} />
          <Field label="Emergency contact phone" value={patient.emergency_contact_phone} />
        </div>
      </div>

      <div className="section-title">Appointments</div>
      <div className="card">
        {appointments.length === 0 && <div className="empty">No appointments booked.</div>}
        {appointments.map((a) => (
          <div
            key={a.appointment_id}
            style={{ display: "flex", justifyContent: "space-between", padding: "8px 0" }}
          >
            <span className="field-value">{a.label}</span>
            <span className="badge good">{a.status}</span>
          </div>
        ))}
      </div>

      <div className="section-title">Call history</div>
      <div className="card">
        {logs.length === 0 && <div className="empty">No calls linked to this patient yet.</div>}
        {logs.map((log) => (
          <div key={log.call_id} style={{ marginBottom: 16 }}>
            <div className="field-label">{new Date(log.created_at).toLocaleString()}</div>
            <div className="field-value">{log.summary || "No summary available"}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
