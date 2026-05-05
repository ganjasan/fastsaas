/**
 * Breadcrumb resolves the current section from a known URL match.
 *
 * The component reads the active pathname via `useRouterState`. We mock that
 * hook to feed it a path and assert the rendered label.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Breadcrumb } from "./Breadcrumb";

vi.mock("@tanstack/react-router", () => ({
  useRouterState: vi.fn(),
}));

import { useRouterState } from "@tanstack/react-router";
const mockedUseRouterState = vi.mocked(useRouterState);

describe("Breadcrumb", () => {
  it.each([
    ["/orgs/acme", "Overview"],
    ["/orgs/acme/", "Overview"],
    ["/orgs/acme/projects", "Projects"],
    ["/orgs/acme/projects/q4", "Project"],
    ["/orgs/acme/settings", "Settings"],
    ["/orgs/acme/settings/members", "Members"],
    ["/orgs/acme/settings/branding", "Branding"],
  ])("path %s → label %s", (path, expected) => {
    mockedUseRouterState.mockReturnValue(path);
    render(<Breadcrumb />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("renders nothing for unrecognised paths", () => {
    mockedUseRouterState.mockReturnValue("/orgs");
    const { container } = render(<Breadcrumb />);
    expect(container).toBeEmptyDOMElement();
  });
});
