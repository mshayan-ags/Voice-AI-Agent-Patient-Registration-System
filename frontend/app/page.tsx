"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listPatients, type Patient } from "@/lib/api";

export default function PatientsPage() {
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load(filter?: string) {
    try {
      setError(null);
      const data = await listPatients(filter ? { last_name: filter } : {});
      setPatients(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patients");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="container">
      <div className="header">
        <div>
          <h1>Registered Patients</h1>
          <p>Live from MongoDB via the FastAPI service — same data the voice agent writes to.</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="badge">{patients?.length ?? 0} patients</span>
          <Link href="/calls">Call logs &rarr;</Link>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(lastName);
          }}
          style={{ display: "flex", gap: 8 }}
        >
          <input
            placeholder="Filter by last name…"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
          />
          <button type="submit">Search</button>
          {lastName && (
            <button
              type="button"
              onClick={() => {
                setLastName("");
                load();
              }}
            >
              Clear
            </button>
          )}
        </form>
      </div>

      <div className="card">
        {error && <div className="empty">Error: {error}</div>}
        {!error && patients === null && <div className="empty">Loading…</div>}
        {!error && patients?.length === 0 && <div className="empty">No patients yet.</div>}
        {!error && patients && patients.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>DOB</th>
                <th>Phone</th>
                <th>City, State</th>
                <th>Registered</th>
              </tr>
            </thead>
            <tbody>
              {patients.map((p) => (
                <tr key={p.patient_id}>
                  <td>
                    <Link href={`/patients/${p.patient_id}`}>
                      {p.first_name} {p.last_name}
                    </Link>
                  </td>
                  <td>{p.date_of_birth}</td>
                  <td>{p.phone_number}</td>
                  <td>
                    {p.city}, {p.state}
                  </td>
                  <td>{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
