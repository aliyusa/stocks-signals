import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Disclaimer } from "../components/ui";

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <span className="text-lg font-bold">Halal Stock Signals</span>
        </div>
        <div className="rounded-xl border border-ink-800 bg-ink-900 p-6">
          <h1 className="mb-4 text-base font-semibold">{title}</h1>
          {children}
        </div>
        <div className="mt-6"><Disclaimer /></div>
      </div>
    </div>
  );
}

const input = "w-full rounded-lg border border-ink-700 bg-ink-950 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:border-brand-500 focus:outline-none";
const btn = "w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-500 disabled:opacity-60";

export function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Sign in">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-xs text-ink-300">Email
          <input className={`${input} mt-1`} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block text-xs text-ink-300">Password
          <input className={`${input} mt-1`} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
        <button className={btn} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <p className="mt-4 text-xs text-ink-400">No account? <Link to="/register" className="text-brand-500 hover:underline">Create one</Link></p>
    </Shell>
  );
}

export function RegisterPage() {
  const { user, register } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(f.email, f.password, f.name);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Create account">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-xs text-ink-300">Full name
          <input className={`${input} mt-1`} autoComplete="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </label>
        <label className="block text-xs text-ink-300">Email
          <input className={`${input} mt-1`} type="email" autoComplete="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </label>
        <label className="block text-xs text-ink-300">Password
          <input className={`${input} mt-1`} type="password" autoComplete="new-password" minLength={10} required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <span className="mt-1 block text-[11px] text-ink-500">At least 10 characters, with letters and digits.</span>
        </label>
        {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
        <button className={btn} disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      <p className="mt-4 text-xs text-ink-400">Already registered? <Link to="/login" className="text-brand-500 hover:underline">Sign in</Link></p>
    </Shell>
  );
}
