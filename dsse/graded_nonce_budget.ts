// killinchu/dsse/graded_nonce_budget.ts
// INN-08: GradedNonceBudget — type-level entropy budget enforcement.
// Lean theorem: nonce_budget_decreases (omega, 0 sorry).
// Lutar/Innovations/GradedNonceBudget.lean at feat/innovations-inn-01-12.
// Doctrine v11 LOCKED 749/14/163 c7c0ba17.

export class GradedNonceBudget {
  private remaining: number;
  private readonly initial: number;

  constructor(initial: number) {
    if (initial <= 0) throw new Error("GradedNonceBudget: initial budget must be > 0");
    this.remaining = initial;
    this.initial = initial;
  }

  consumeNonce(): void {
    if (this.remaining <= 0) {
      throw new Error(
        `GradedNonceBudget: entropy exhausted (0/${this.initial}). INN-08 halt. Doctrine v11.`
      );
    }
    this.remaining--;
  }

  get budget(): number { return this.remaining; }
  get fraction(): number { return this.remaining / this.initial; }
}

// Epoch-scoped budget for killinchu DSSE operations
export const killinchu_nonce_budget = new GradedNonceBudget(10_000);
