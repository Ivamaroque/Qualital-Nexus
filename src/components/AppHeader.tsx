"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import qualitalEntireLogo from "@/app/assets/Qualital_entire_logo.png";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";

type AppHeaderProps = {
  title: string;
};

export function AppHeader({ title }: AppHeaderProps) {
  const router = useRouter();

  async function handleLogout() {
    const supabase = getSupabaseBrowserClient();

    if (supabase) {
      await supabase.auth.signOut();
    }

    router.replace("/login");
  }

  return (
    <header aria-label={`Navegação de ${title}`} className="app-navigation">
      <Link
        aria-label="Ir para o hub de ferramentas"
        className="app-navigation__brand"
        href="/dashboard"
      >
        <Image
          alt="Qualital"
          className="app-navigation__logo"
          priority
          src={qualitalEntireLogo}
        />
        <span aria-hidden="true" className="app-navigation__separator" />
        <span>Hub de ferramentas</span>
      </Link>

      <button
        aria-label="Sair da conta"
        className="app-navigation__logout"
        onClick={handleLogout}
        type="button"
      >
        <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
          <path
            d="M10 17l5-5-5-5M15 12H3"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
          <path
            d="M21 4v16a1 1 0 0 1-1 1h-8"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.8"
          />
        </svg>
        <span>Sair</span>
      </button>
    </header>
  );
}
