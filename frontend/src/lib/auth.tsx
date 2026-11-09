import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, clearSession, getToken, getUser, saveSession, type User } from "./api";

type AuthCtx = {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => (getToken() ? getUser() : null));

  // 启动时校验令牌与账号状态：被停用则立即失效
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.me()
      .then((u) => {
        const fresh: User = { ...u, name: u.display_name ?? u.email };
        saveSession(token, fresh);
        setUser(fresh);
      })
      .catch(() => {
        clearSession();
        setUser(null);
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    const u: User = { ...res.user, name: res.user.display_name ?? res.user.email };
    saveSession(res.token, u);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
