"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();

    if (!supabase) {
      setMessage("Configuração do Supabase ausente. Defina NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        router.replace("/dashboard");
      }
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        router.replace("/dashboard");
      }
    });

    return () => {
      subscription.subscription.unsubscribe();
    };
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);

    try {
      const supabase = getSupabaseBrowserClient();

      if (!supabase) {
        setMessage("Configuração do Supabase ausente. Defina NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_ANON_KEY.");
        return;
      }

      const { error } = await supabase.auth.signInWithPassword({
        email,
        password
      });

      if (error) {
        const friendlyError =
          error.message === "Invalid login credentials"
            ? "E-mail ou senha inválidos. Verifique os dados e tente novamente."
            : "Não foi possível entrar agora. Tente novamente em instantes.";
        setMessage(friendlyError);
        return;
      }

      router.replace("/dashboard");
    } catch {
      setMessage("Não foi possível conectar ao serviço de autenticação. Verifique as variáveis do Supabase.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell page-shell--centered">
      <div className="container">
        <div className="surface card hero grid grid--two" style={{ alignItems: "stretch" }}>
          <section className="stack stack--xl" style={{ justifyContent: "center" }}>
            <div className="brand">
              <div className="brand__mark">QN</div>
              <div>
                <div style={{ fontSize: "1.1rem" }}>Qualital Nexus</div>
                <div className="text text--xs">Plataforma interna da Qualital</div>
              </div>
            </div>

            <div className="stack" style={{ gap: 12 }}>
              <p className="eyebrow">Acesso interno</p>
              <h1 className="title title--xl">Entre para operar as ferramentas corporativas.</h1>
              <p className="text text--sm">
                A primeira versão já abre o dashboard e a ferramenta de Extração PDF com fila ordenável, estados de processamento e download do CSV.
              </p>
            </div>

            <div className="panel stack" style={{ maxWidth: 440 }}>
              <p className="text text--strong">Foco do MVP</p>
              <p className="text text--sm">Autenticação com Supabase, lista local de ferramentas e integração preparada para o backend Python/FastAPI.</p>
            </div>
          </section>

          <section className="surface surface--solid card stack" style={{ justifyContent: "center" }}>
            <div className="stack" style={{ gap: 10 }}>
              <p className="eyebrow">Login</p>
              <h2 className="title title--lg">Acessar o sistema</h2>
              <p className="text text--sm">Use o e-mail e senha cadastrados no Supabase Auth.</p>
            </div>

            {message ? <div className="alert alert--error">{message}</div> : null}

            <form className="stack" onSubmit={handleSubmit}>
              <label className="field">
                <span className="label">E-mail</span>
                <input
                  className="input"
                  name="email"
                  type="email"
                  placeholder="nome@qualital.com.br"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  required
                />
              </label>

              <label className="field">
                <span className="label">Senha</span>
                <input
                  className="input"
                  name="password"
                  type="password"
                  placeholder="Digite sua senha"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>

              <button className="button button--primary" type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <span className="spinner" aria-hidden="true" />
                    Entrando
                  </>
                ) : (
                  "Entrar"
                )}
              </button>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}