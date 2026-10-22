# Supabase Auth & Email Verification Branding Guide

Follow these steps in your Supabase project dashboard to ensure all verification emails display **AI Site Engineer** and match your executive construction intelligence branding.

---

## 1. Customizing the Email Template (Subject & Body)

1. Open your **[Supabase Dashboard](https://supabase.com/dashboard)** and select your project.
2. In the left navigation, go to **Authentication** > **Email Templates**.
3. Click on the **"Confirm signup"** tab.
4. Update the fields as follows:

### Subject:
```text
Confirm your AI Site Engineer account
```

### Message Body (HTML):
Copy and paste the exact contents of:
👉 [`docs/email_templates/confirmation_email.html`](email_templates/confirmation_email.html)

> **Note on Variables:**  
> Supabase automatically replaces `{{ .ConfirmationURL }}` in the template with the secure one-time verification link pointing back to your app.

---

## 2. Setting Sender Name & Sender Email

Under **Authentication** > **Email Templates**:

* **Sender Name:**  
  Set to `AI Site Engineer` (instead of the default `Supabase`).
* **Sender Email:**  
  If using custom SMTP, set to `no-reply@yourdomain.com` or `welcome@aisiteengineer.com`.

---

## 3. Configuring Custom SMTP (Remove Supabase Domain Completely)

By default, Supabase's free built-in email service has a limit of 3-4 emails per hour and comes from `noreply@mail.app.supabase.io`.

For professional production delivery:
1. In Supabase Dashboard, navigate to **Project Settings** > **Authentication** > **SMTP Settings**.
2. Toggle on **"Enable Custom SMTP"**.
3. Choose any standard SMTP provider (e.g. **Resend** (recommended, 3,000 free emails/mo), **SendGrid**, or **Brevo**):
   * **Sender Email:** `no-reply@yourdomain.com`
   * **Sender Name:** `AI Site Engineer`
   * **Host:** `smtp.resend.com` (port `465` or `587`)
   * **Username:** `resend`
   * **Password:** `re_your_api_key_here`
4. Click **Save**. All verification emails will now arrive from `AI Site Engineer <no-reply@yourdomain.com>` with zero mention of Supabase.

---

## 4. Setting Redirect & Callback URLs

In **Authentication** > **URL Configuration**:

* **Site URL:**  
  `https://your-app.vercel.app` (or `http://localhost:3000` for development).
* **Redirect URLs:**  
  Add:
  - `https://your-app.vercel.app/auth/callback`
  - `http://localhost:3000/auth/callback`

When the site engineer clicks the confirmation button in their email, they will be redirected to `/auth/callback`, which automatically exchanges their token for a logged-in session and takes them directly into the Engineering Workspace with their saved drawings ready!
