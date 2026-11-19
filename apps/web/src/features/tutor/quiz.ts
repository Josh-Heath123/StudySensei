/**
 * "Quiz me", graded here, in code: the model writes the questions, never the marks (and no
 * mastery or plan changes: that's Phase 5). The API stores the student's picks.
 */
import type { components } from "@/lib/api/schema";

export type Quiz = components["schemas"]["Quiz"];
export type QuizQuestion = components["schemas"]["QuizQuestion"];
export type QuizAnswers = (number | null)[];

/** How many questions a quiz asks for (the API keeps only grounded ones, so maybe fewer). */
export const QUIZ_SIZE = 3;

export const isRight = (question: QuizQuestion, pick: number | null | undefined) =>
  pick !== null && pick !== undefined && pick === question.correct;

/** The first question not answered yet, or the question count when all are. */
export function firstUnanswered(quiz: Quiz, answers: QuizAnswers): number {
  const index = quiz.questions.findIndex((_, i) => answers[i] === null || answers[i] === undefined);
  return index === -1 ? quiz.questions.length : index;
}

/** Right answers out of the questions answered so far. */
export function score(quiz: Quiz, answers: QuizAnswers): { right: number; answered: number } {
  let right = 0;
  let answered = 0;
  quiz.questions.forEach((question, i) => {
    const pick = answers[i];
    if (pick === null || pick === undefined) return;
    answered += 1;
    if (isRight(question, pick)) right += 1;
  });
  return { right, answered };
}

/** The picks with one more answer: a new array, the same length as the quiz. */
export function withAnswer(quiz: Quiz, answers: QuizAnswers, index: number, pick: number) {
  return quiz.questions.map((_, i) => (i === index ? pick : (answers[i] ?? null)));
}

export const LETTERS = ["A", "B", "C", "D"] as const;
