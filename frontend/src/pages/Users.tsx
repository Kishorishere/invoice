import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import {
  Check,
  KeyRound,
  Mail,
  MoreHorizontal,
  Pencil,
  ShieldCheck,
  Trash2,
  UserPlus,
  X as XIcon,
} from "lucide-react";
import { toast } from "sonner";

import { AppLayout } from "@/components/AppLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AdminUserRow, Role } from "@/lib/types";
import { cn, formatDate, relativeTime } from "@/lib/utils";

type DialogState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; user: AdminUserRow }
  | { kind: "reset"; user: AdminUserRow }
  | { kind: "delete"; user: AdminUserRow };

export function Users() {
  const { user: me } = useAuth();
  const [rows, setRows] = useState<AdminUserRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>({ kind: "closed" });

  const load = useCallback(async () => {
    try {
      setRows(await api.listUsers());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load users.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const close = () => setDialog({ kind: "closed" });
  const onChanged = async () => {
    close();
    await load();
  };

  const sorted = useMemo(
    () => (rows ? [...rows].sort((a, b) => a.email.localeCompare(b.email)) : null),
    [rows]
  );

  return (
    <AppLayout>
      <div className="mx-auto max-w-5xl pt-6 sm:pt-10 animate-fade-in">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-4xl sm:text-5xl">Users</h1>
            <p className="mt-1 text-muted-foreground">
              Invite your team. Admins can do everything; users can only see their own invoices.
            </p>
          </div>
          <Button onClick={() => setDialog({ kind: "create" })}>
            <UserPlus className="h-4 w-4" />
            Add user
          </Button>
        </header>

        {error && (
          <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {sorted === null && !error && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-14 animate-pulse-soft rounded-xl bg-muted/50" />
            ))}
          </div>
        )}

        {sorted && sorted.length === 0 && (
          <div className="rounded-2xl border border-border bg-card p-8 text-center shadow-soft">
            <p className="text-sm text-muted-foreground">No users yet.</p>
          </div>
        )}

        {sorted && sorted.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left font-medium">Email</th>
                  <th className="px-4 py-3 text-left font-medium">Role</th>
                  <th className="px-4 py-3 text-right font-medium">Invoices</th>
                  <th className="px-4 py-3 text-left font-medium">Added</th>
                  <th className="w-10 px-2" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((u, i) => (
                  <motion.tr
                    key={u.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.02 }}
                    className="border-b border-border/70 last:border-0 transition-colors hover:bg-muted/30"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-medium">
                          {u.email[0]?.toUpperCase() ?? "?"}
                        </span>
                        <span className="font-medium">{u.email}</span>
                        {u.id === me?.id && (
                          <Badge variant="secondary" className="text-[10px]">
                            you
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {u.role === "admin" ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                          <ShieldCheck className="h-3 w-3" /> admin
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">user</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-muted-foreground">
                      {u.invoice_count}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      <span title={formatDate(u.created_at)}>{relativeTime(u.created_at)}</span>
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RowMenu
                        user={u}
                        isSelf={u.id === me?.id}
                        onEdit={() => setDialog({ kind: "edit", user: u })}
                        onReset={() => setDialog({ kind: "reset", user: u })}
                        onDelete={() => setDialog({ kind: "delete", user: u })}
                      />
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <CreateUserDialog
        open={dialog.kind === "create"}
        onClose={close}
        onSuccess={onChanged}
      />
      {dialog.kind === "edit" && (
        <EditUserDialog user={dialog.user} isSelf={dialog.user.id === me?.id} onClose={close} onSuccess={onChanged} />
      )}
      {dialog.kind === "reset" && (
        <ResetPasswordDialog user={dialog.user} onClose={close} onSuccess={close} />
      )}
      {dialog.kind === "delete" && (
        <DeleteUserDialog user={dialog.user} onClose={close} onSuccess={onChanged} />
      )}
    </AppLayout>
  );
}

function RowMenu({
  user,
  isSelf,
  onEdit,
  onReset,
  onDelete,
}: {
  user: AdminUserRow;
  isSelf: boolean;
  onEdit: () => void;
  onReset: () => void;
  onDelete: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ring-focus"
          aria-label={`Actions for ${user.email}`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[12rem]">
        <DropdownMenuLabel className="truncate">{user.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onEdit}>
          <Pencil className="h-4 w-4" /> Edit email / role
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onReset}>
          <KeyRound className="h-4 w-4" /> Reset password
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={onDelete}
          disabled={isSelf}
          className={cn("text-destructive", isSelf && "cursor-not-allowed opacity-50")}
        >
          <Trash2 className="h-4 w-4" /> Delete user
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------- Dialogs ----------------

function CreateUserDialog({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => Promise<void> | void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setEmail("");
      setPassword("");
      setRole("user");
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await api.createUser({ email, password, role });
      toast.success(`Invited ${email}`);
      await onSuccess();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't create user.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a new user</DialogTitle>
          <DialogDescription>
            Set their email and a permanent password. They'll use these to sign in.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <Field label="Email" icon={<Mail className="h-3.5 w-3.5" />}>
            <Input
              type="email"
              autoComplete="off"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@company.com"
            />
          </Field>
          <Field label="Password (permanent)" icon={<KeyRound className="h-3.5 w-3.5" />}>
            <PasswordInput
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="font-mono"
              defaultVisible
            />
          </Field>
          <RoleToggle value={role} onChange={setRole} />
          <div className="flex items-center justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Creating…" : "Create user"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditUserDialog({
  user,
  isSelf,
  onClose,
  onSuccess,
}: {
  user: AdminUserRow;
  isSelf: boolean;
  onClose: () => void;
  onSuccess: () => Promise<void> | void;
}) {
  const { refresh } = useAuth();
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState<Role>(user.role);
  const [busy, setBusy] = useState(false);

  const emailChanged = email.trim().toLowerCase() !== user.email.toLowerCase();
  const roleChanged = role !== user.role;
  const dirty = emailChanged || roleChanged;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!dirty) return;
    setBusy(true);
    try {
      await api.updateUser(user.id, {
        email: emailChanged ? email : undefined,
        role: roleChanged ? role : undefined,
      });
      toast.success("Saved");
      // If we just edited ourselves, refresh the auth context.
      if (isSelf) await refresh();
      await onSuccess();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't save changes.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit user</DialogTitle>
          <DialogDescription>{user.email}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <Field label="Email" icon={<Mail className="h-3.5 w-3.5" />}>
            <Input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <RoleToggle value={role} onChange={setRole} disabledAdminLock={isSelf} />
          {isSelf && (
            <p className="text-xs text-muted-foreground">
              You can't remove your own admin role. Ask another admin.
            </p>
          )}
          <div className="flex items-center justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={busy || !dirty}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({
  user,
  onClose,
  onSuccess,
}: {
  user: AdminUserRow;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await api.resetUserPassword(user.id, password);
      toast.success(`New password set for ${user.email}`);
      onSuccess();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't reset password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reset password</DialogTitle>
          <DialogDescription>
            Set a new permanent password for <span className="font-medium text-foreground">{user.email}</span>.
            Share it with them securely.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <Field label="New password" icon={<KeyRound className="h-3.5 w-3.5" />}>
            <PasswordInput
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="font-mono"
              autoFocus
              defaultVisible
            />
          </Field>
          <div className="flex items-center justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Resetting…" : "Set new password"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteUserDialog({
  user,
  onClose,
  onSuccess,
}: {
  user: AdminUserRow;
  onClose: () => void;
  onSuccess: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);

  const onConfirm = async () => {
    setBusy(true);
    try {
      await api.deleteUser(user.id);
      toast.success(`Deleted ${user.email}`);
      await onSuccess();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't delete user.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {user.email}?</DialogTitle>
          <DialogDescription>
            This removes the account and all {user.invoice_count} of their invoice{user.invoice_count === 1 ? "" : "s"}. This can't be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center justify-end gap-2 pt-2">
          <DialogClose asChild>
            <Button type="button" variant="ghost" size="sm">
              Cancel
            </Button>
          </DialogClose>
          <Button variant="destructive" size="sm" onClick={onConfirm} disabled={busy}>
            {busy ? "Deleting…" : "Delete user"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------- Small shared bits ----------------

function Field({
  label,
  icon,
  children,
}: {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="flex items-center gap-1.5 text-muted-foreground">
        {icon}
        {label}
      </Label>
      {children}
    </div>
  );
}

function RoleToggle({
  value,
  onChange,
  disabledAdminLock = false,
}: {
  value: Role;
  onChange: (r: Role) => void;
  disabledAdminLock?: boolean;
}) {
  return (
    <div>
      <Label className="mb-1.5 block text-muted-foreground">Role</Label>
      <div className="inline-flex items-center gap-1 rounded-xl border border-border bg-muted/40 p-1">
        {(["user", "admin"] as Role[]).map((r) => {
          const active = value === r;
          const disabled = disabledAdminLock && r !== "admin" && value === "admin";
          return (
            <button
              type="button"
              key={r}
              disabled={disabled}
              onClick={() => onChange(r)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ring-focus",
                active
                  ? "bg-card text-foreground shadow-soft"
                  : "text-muted-foreground hover:text-foreground",
                disabled && "cursor-not-allowed opacity-50"
              )}
            >
              {active ? <Check className="h-3 w-3 text-primary" /> : <XIcon className="h-3 w-3 opacity-0" />}
              {r === "admin" ? (
                <span className="inline-flex items-center gap-1">
                  <ShieldCheck className="h-3 w-3" /> Admin
                </span>
              ) : (
                "User"
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
