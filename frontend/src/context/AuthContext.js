// src/context/AuthContext.js — Provides Firebase auth state to the whole app.
"use client";

import { createContext, useContext, useEffect, useState } from "react";
import {GoogleAuthProvider, onAuthStateChanged,signInWithPopup, signOut} from "firebase/auth";
import { auth } from "@/lib/firebase";

const AuthContext = createContext(null);

const FORCE_ACCOUNT_CHOOSER_KEY = "forceGoogleAccountChooser";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser ?? null);
    });
    return unsubscribe;
  }, []);

  const login = async () => {
    const provider = new GoogleAuthProvider();

    if (
      localStorage.getItem(FORCE_ACCOUNT_CHOOSER_KEY) === "true"
    ) {
      provider.setCustomParameters({
        prompt: "select_account",
      });
    }

    await signInWithPopup(auth, provider);

    localStorage.removeItem(FORCE_ACCOUNT_CHOOSER_KEY);
  };

  const logout = async () => {
    localStorage.setItem(FORCE_ACCOUNT_CHOOSER_KEY, "true");
    await signOut(auth);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
