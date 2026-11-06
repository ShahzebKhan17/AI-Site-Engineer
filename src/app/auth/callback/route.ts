import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type");
  const next = searchParams.get("next") || "/";

  // Forward auth tokens to client so browser-side Supabase client can exchange
  // and persist the active session directly into localStorage
  const targetParams = new URLSearchParams();
  if (code) targetParams.set("code", code);
  if (tokenHash) targetParams.set("token_hash", tokenHash);
  if (type) targetParams.set("type", type);
  if (type === "recovery" || next.includes("reset_password=true")) {
    targetParams.set("reset_password", "true");
  }

  const query = targetParams.toString();
  return NextResponse.redirect(`${origin}/${query ? `?${query}` : ""}`);
}
