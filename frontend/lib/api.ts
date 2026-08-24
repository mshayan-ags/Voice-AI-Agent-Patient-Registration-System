const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "https://carecloud-backend.onrender.com";

export type Patient = {
  patient_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  sex: string;
  phone_number: string;
  email?: string | null;
  address_line_1: string;
  address_line_2?: string | null;
  city: string;
  state: string;
  zip_code: string;
  insurance_provider?: string | null;
  insurance_member_id?: string | null;
  preferred_language: string;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  created_at: string;
  updated_at: string;
};

export type StructuredCallData = {
  patient_first_name?: string;
  patient_last_name?: string;
  caller_intent?: string;
  registration_completed?: boolean;
  existing_patient_recognized?: boolean;
  appointment_booked?: boolean;
};

export type CallLog = {
  call_id: string;
  patient_id: string | null;
  transcript: unknown;
  summary: string | null;
  structured_data?: StructuredCallData | null;
  success_evaluation?: string | boolean | null;
  ended_reason?: string | null;
  created_at: string;
};

export type Appointment = {
  appointment_id: string;
  patient_id: string;
  patient_name: string | null;
  label: string;
  reason: string | null;
  status: string;
  created_at: string;
};

type Envelope<T> = { data: T | null; error: { code: string; message: string } | null };

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    // ngrok's free tier shows an HTML interstitial to browser-like requests
    // unless this header is present; harmless against a real deployed host.
    headers: { "ngrok-skip-browser-warning": "true" },
  });
  const body: Envelope<T> = await res.json();
  if (!res.ok || body.error) {
    throw new Error(body.error?.message || `Request to ${path} failed`);
  }
  return body.data as T;
}

export function listPatients(params: { last_name?: string; phone_number?: string } = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => Boolean(v)) as [string, string][]
  ).toString();
  return request<Patient[]>(`/patients${qs ? `?${qs}` : ""}`);
}

export function getPatient(id: string) {
  return request<Patient>(`/patients/${id}`);
}

export function listCallLogs(patientId?: string) {
  return request<CallLog[]>(patientId ? `/call-logs?patient_id=${patientId}` : "/call-logs");
}

export function listAppointments(patientId?: string) {
  return request<Appointment[]>(
    patientId ? `/appointments?patient_id=${patientId}` : "/appointments"
  );
}
