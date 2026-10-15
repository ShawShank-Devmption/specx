/** Errors the sandbox HTTP layer turns into `{error: {code, message}}` with the given status. */
export class SandboxError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}
