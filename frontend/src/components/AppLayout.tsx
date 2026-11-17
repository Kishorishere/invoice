import { useNavigate } from "react-router-dom";
import { LogOut, ShieldCheck } from "lucide-react";

import { QuotaMeter } from "@/components/QuotaMeter";
import { Sidebar } from "@/components/Sidebar";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";

interface Props {
  rightTop?: React.ReactNode;
  children: React.ReactNode;
}

export function AppLayout({ rightTop, children }: Props) {
  const { user, isAdmin, logout } = useAuth();
  const nav = useNavigate();

  const onLogout = async () => {
    await logout();
    nav("/login", { replace: true });
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-10 items-center justify-end gap-2 px-8">
          <div className="min-w-0 flex-1">{rightTop}</div>
          <div className="flex items-center gap-2">
            {user && <QuotaMeter />}
            <ThemeToggle />
            {user && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    className="relative flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-medium transition-colors ring-focus hover:bg-secondary"
                    aria-label="Account menu"
                  >
                    {user.email[0]?.toUpperCase() ?? "?"}
                    {isAdmin && (
                      <span
                        className="absolute -right-0.5 -top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-foreground text-background"
                        title="Admin"
                      >
                        <ShieldCheck className="h-2.5 w-2.5" />
                      </span>
                    )}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[14rem]">
                  <DropdownMenuLabel className="flex items-center justify-between gap-2">
                    <span className="truncate">{user.email}</span>
                    {isAdmin && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        <ShieldCheck className="h-3 w-3" /> admin
                      </span>
                    )}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={onLogout} className="text-destructive">
                    <LogOut className="h-4 w-4" /> Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-8 pb-10">{children}</main>
      </div>
    </div>
  );
}
