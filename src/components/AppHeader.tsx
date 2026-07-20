"use client";

import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";

type AppHeaderProps = {
  title: string;
  subtitle?: string;
  userName: string;
  userEmail?: string | null;
};

function getInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "QN";
}

export function AppHeader({ title, subtitle, userName, userEmail }: AppHeaderProps) {
  const router = useRouter();

  async function handleLogout() {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="surface card card--compact">
      <div className="toolbar">
        <div className="row" style={{ alignItems: "center" }}>
          <div className="brand__mark" aria-hidden="true">
            QN
          </div>
          <div>
            <p className="eyebrow">Qualital Nexus</p>
            <h1 className="title title--lg" style={{ marginTop: 6 }}>
              {title}
            </h1>
            {subtitle ? <p className="text text--sm">{subtitle}</p> : null}
          </div>
        </div>

        <div className="toolbar__actions">
          <div className="panel row" style={{ padding: 12, borderRadius: 999 }}>
            <div className="brand__mark" style={{ width: 38, height: 38, borderRadius: 999, fontSize: "0.8rem" }}>
              {getInitials(userName)}
            </div>
            <div>
              <p className="text text--strong" style={{ marginBottom: 2 }}>
                {userName}
              </p>
              <p className="text text--xs">{userEmail ?? "Usuário autenticado"}</p>
            </div>
          </div>
          <button className="button button--secondary" onClick={handleLogout} type="button">
            Sair da conta
          </button>
        </div>
      </div>
    </header>
  );
}