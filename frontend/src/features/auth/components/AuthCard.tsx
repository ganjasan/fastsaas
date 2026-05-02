/**
 * Centered narrow card used by every /auth/* page. Pure layout — no logic.
 */
import type { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface AuthCardProps {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}

export function AuthCard({ title, description, children }: AuthCardProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}
