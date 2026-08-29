import Link from "next/link";

export function NavBar() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          InsightForge
        </Link>
        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          <Link href="/dashboard" className="hover:text-foreground">
            Dashboard
          </Link>
          <Link href="/analyze" className="hover:text-foreground">
            Analyze
          </Link>
        </nav>
      </div>
    </header>
  );
}
