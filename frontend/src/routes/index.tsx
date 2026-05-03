import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: HelloPage,
});

function HelloPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <div className="space-y-2 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">FastSaaS</h1>
        <p className="text-muted-foreground">platform skeleton — sub-issue #2 bootstrap</p>
      </div>
    </main>
  );
}
