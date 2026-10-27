"use client";

import Link from "next/link";
import { useState } from "react";
import { postWaitlist } from "../lib/api";
import { t, u, type Lang } from "../lib/i18n";

// Position buckets verbatim from dashboard/i18n.py SIZE_BUCKETS.
const SIZE_BUCKETS = ["<$100", "$100–$1,000", "$1,000–$10,000", ">$10,000"];

// Contact must be reachable: an email address, or a Telegram username
// (5–32 chars, letters/digits/underscore, optional leading @). Mirrors
// the waitlist Worker's server-side check; the server check is the one
// that keeps garbage out of the table.
function validContact(c: string): boolean {
  if (c.startsWith("@")) return /^[A-Za-z0-9_]{5,32}$/.test(c.slice(1));
  if (c.includes("@")) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c);
  return /^[A-Za-z0-9_]{5,32}$/.test(c);
}

export default function WaitlistForm({ lang }: { lang: Lang }) {
  const [contact, setContact] = useState("");
  const [position, setPosition] = useState(SIZE_BUCKETS[1]);
  const [venues, setVenues] = useState("");
  const [price, setPrice] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "done" | "error" | "formatError" | "already" | "saveError">("idle");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const c = contact.trim();
    const v = venues.trim();
    // Mirror the server validation (required + consent + length caps).
    if (
      !c ||
      c.length > 200 ||
      !position ||
      position.length > 100 ||
      !v ||
      v.length > 300 ||
      price.trim().length > 100 ||
      !consent
    ) {
      setState("error");
      return;
    }
    if (!validContact(c)) {
      setState("formatError");
      return;
    }
    setState("sending");
    try {
      const res = await postWaitlist({ contact: c, position, venues: v, price: price.trim() || undefined, consent: true });
      setState(res.already ? "already" : "done");
    } catch (err) {
      // The Worker rejects malformed contacts with "invalid contact";
      // surface that as the format message, not a generic save error.
      setState(err instanceof Error && err.message === "invalid contact" ? "formatError" : "saveError");
    }
  };

  if (state === "done") {
    return (
      <div role="status">
        <p>{t(lang, "f_success")}</p>
        <p className="hint">{t(lang, "f_success_detail")}</p>
      </div>
    );
  }

  if (state === "already") {
    return (
      <div role="status">
        <p>{t(lang, "f_already")}</p>
        <p className="hint">{t(lang, "f_success_detail")}</p>
      </div>
    );
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="field">
        <label htmlFor="wl-contact">{t(lang, "f_contact")}</label>
        <input
          id="wl-contact"
          type="text"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          autoComplete="email"
        />
      </div>
      <div className="field">
        <label htmlFor="wl-position">{t(lang, "f_position")}</label>
        <select
          id="wl-position"
          value={position}
          onChange={(e) => setPosition(e.target.value)}
        >
          {SIZE_BUCKETS.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="wl-venues">{t(lang, "f_venues")}</label>
        <input
          id="wl-venues"
          type="text"
          value={venues}
          onChange={(e) => setVenues(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="wl-price">{t(lang, "f_price")}</label>
        <input
          id="wl-price"
          type="text"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
      </div>
      <div className="field check">
        <input
          id="wl-consent"
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        <label htmlFor="wl-consent">{t(lang, "f_consent")}</label>
      </div>
      {state === "error" && (
        <p className="formerror" role="alert">
          {t(lang, "f_error")}
        </p>
      )}
      {state === "formatError" && (
        <p className="formerror" role="alert">
          {t(lang, "f_error_format")}
        </p>
      )}
      {state === "saveError" && (
        <p className="formerror" role="alert">
          {t(lang, "f_error_save")}
        </p>
      )}
      <button type="submit" className="btn" disabled={state === "sending"}>
        {state === "sending" ? u(lang, "waitlist_sending") : t(lang, "f_submit")}
      </button>
      <p className="hint">
        {t(lang, "waitlist_privacy")}{" "}
        <Link href="/methodology">{t(lang, "waitlist_methodology_btn")}</Link>
      </p>
    </form>
  );
}
