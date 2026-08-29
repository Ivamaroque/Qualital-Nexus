"use client";

import { FormEvent, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import qLogo from "@/app/assets/Q_logo.png";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";

const AUTH_REQUEST_TIMEOUT_MS = 15000;

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
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

      const { error } = await Promise.race([
        supabase.auth.signInWithPassword({
          email,
          password
        }),
        new Promise<never>((_, reject) => {
          window.setTimeout(() => {
            reject(new Error("O serviço de autenticação demorou para responder."));
          }, AUTH_REQUEST_TIMEOUT_MS);
        })
      ]);

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
    <main className="login-page">
      <div className="login-layout">
        <section className="login-institutional" aria-labelledby="login-institutional-title">
          <div className="login-institutional__glow login-institutional__glow--top" aria-hidden="true" />
          <div className="login-institutional__glow login-institutional__glow--bottom" aria-hidden="true" />

          <div className="login-identity">
            <div className="login-identity__mark">
              <Image alt="" priority src={qLogo} />
            </div>
            <div>
              <p className="login-identity__name">Qualital Nexus</p>
              <p className="login-identity__subtitle">Plataforma interna</p>
            </div>
          </div>

          <div className="login-institutional__content">
            <span className="login-kicker">Acesso interno</span>
            <h1 id="login-institutional-title">Entre para operar as ferramentas.</h1>
            <p className="login-institutional__description">
              Acesse o hub corporativo. A ferramenta de extração de documentos possui fila ordenável,
              estados de processamento e download estruturado.
            </p>

          </div>

          <p className="login-copyright">© 2026 Qualital Engenharia e Sustentabilidade</p>
        </section>

        <section className="login-form-panel" aria-labelledby="login-form-title">
          <div className="login-form">
            <header className="login-form__header">
              <h2 id="login-form-title">Acesso ao Sistema</h2>
              <p>Insira suas credenciais corporativas.</p>
            </header>

            {message ? (
              <div className="alert alert--error" role="alert">
                {message}
              </div>
            ) : null}

            <form className="login-form__fields" onSubmit={handleSubmit}>
              <label className="login-field">
                <span>E-mail corporativo</span>
                <span className="login-input-wrap">
                  <span aria-hidden="true" className="login-input-icon">✉</span>
                  <input
                    autoComplete="email"
                    className="login-input"
                    name="email"
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="nome@qualital.com.br"
                    required
                    type="email"
                    value={email}
                  />
                </span>
              </label>

              <label className="login-field">
                <span>Senha</span>
                <span className="login-input-wrap">
                  <span aria-hidden="true" className="login-input-icon">●</span>
                  <input
                    autoComplete="current-password"
                    className="login-input login-input--password"
                    name="password"
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Digite sua senha"
                    required
                    type={isPasswordVisible ? "text" : "password"}
                    value={password}
                  />
                  <button
                    aria-label={isPasswordVisible ? "Ocultar senha" : "Exibir senha"}
                    aria-pressed={isPasswordVisible}
                    className="login-password-toggle"
                    onClick={() => setIsPasswordVisible((current) => !current)}
                    type="button"
                  >
                    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                      <path
                        d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                      />
                      {isPasswordVisible ? (
                        <path
                          d="m4 4 16 16"
                          stroke="currentColor"
                          strokeLinecap="round"
                          strokeWidth="1.8"
                        />
                      ) : (
                        <circle cx="12" cy="12" r="2.5" fill="currentColor" />
                      )}
                    </svg>
                  </button>
                </span>
              </label>

              <div className="login-form__options">
                <label className="login-checkbox">
                  <input defaultChecked type="checkbox" />
                  <span>Manter conectado</span>
                </label>
                <a href="mailto:suporte@qualital.com.br?subject=Recuperação%20de%20senha%20-%20Qualital%20Nexus">
                  Esqueceu a senha?
                </a>
              </div>

              <button className="login-submit" disabled={loading} type="submit">
                {loading ? (
                  <>
                    <span className="spinner" aria-hidden="true" />
                    Entrando…
                  </>
                ) : (
                  <>
                    Entrar no Nexus
                    <span aria-hidden="true">→</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </section>
      </div>
    </main>
  );
}