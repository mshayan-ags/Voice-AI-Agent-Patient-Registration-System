"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Patients" },
  { href: "/appointments", label: "Appointments" },
  { href: "/calls", label: "Call Logs" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <div className="nav">
      <div className="nav-inner">
        <Link href="/" className="nav-brand">
          CareCloud
        </Link>
        <div className="nav-links">
          {LINKS.map((link) => {
            const isActive =
              link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`nav-link${isActive ? " active" : ""}`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
