/** An API call that came back with an error status. `message` is safe to show the user. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

/** Turn a FastAPI error body (`{detail: string}` or a Pydantic issue list) into one sentence. */
export function messageFromBody(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        const msg = (issue.msg ?? "Invalid value").replace(/^Value error, /, "");
        const field = issue.loc?.filter((part) => part !== "body").join(".");
        return field && !msg.startsWith(field) ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return "Something went wrong. Please try again.";
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/** Await an openapi-fetch call: return its data, or throw an ApiError. */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, messageFromBody(error));
  return data as T;
}
