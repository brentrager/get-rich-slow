"use server";

import { cookies } from "next/headers";

const PASSWORD = process.env.DASHBOARD_PASSWORD || "";
const COOKIE_NAME = "predictions_auth";
const COOKIE_VALUE = "authenticated";

export async function login(password: string): Promise<{ success: boolean }> {
  if (password === PASSWORD) {
    const cookieStore = await cookies();
    cookieStore.set(COOKIE_NAME, COOKIE_VALUE, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
      path: "/",
    });
    return { success: true };
  }
  return { success: false };
}

export async function checkAuth(): Promise<boolean> {
  const cookieStore = await cookies();
  return cookieStore.get(COOKIE_NAME)?.value === COOKIE_VALUE;
}

export async function logout(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}
