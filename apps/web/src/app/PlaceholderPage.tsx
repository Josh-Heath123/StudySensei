import { PageHeader } from "./PageHeader";

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return <PageHeader title={title} description={description} />;
}
