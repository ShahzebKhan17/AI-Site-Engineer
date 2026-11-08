import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export async function POST(req: NextRequest) {
  try {
    const { email, password, full_name, organization } = await req.json();
    if (!email || !password) {
      return NextResponse.json({ error: "Email and password are required." }, { status: 400 });
    }

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

    if (!supabaseUrl || !serviceRoleKey) {
      return NextResponse.json(
        { error: "Supabase service role credentials not configured in server environment." },
        { status: 500 }
      );
    }

    const supabaseAdmin = createClient(supabaseUrl, serviceRoleKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    });

    const { data, error } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
      user_metadata: {
        full_name: full_name || "Civil Site Engineer",
        organization: organization || "AI Site Engineer Workspace",
      },
    });

    if (error) {
      // If user already registered, return friendly message
      if (error.message.includes("already registered") || error.message.includes("already exists")) {
        return NextResponse.json(
          { error: "An account with this email already exists. Please sign in instead." },
          { status: 400 }
        );
      }
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({ user: data.user, success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Failed to create user account." }, { status: 500 });
  }
}

