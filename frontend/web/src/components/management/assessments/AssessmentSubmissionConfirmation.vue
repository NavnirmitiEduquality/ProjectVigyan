
<script setup lang="ts">
import type { Assessment } from '../../../services/assessments'

defineProps<{
  assessment: Assessment
}>()

const emit = defineEmits<{
  viewResults: []
  backToDirectory: []
}>()
</script>

<template>
  <section class="submission-confirmation">
    <nav class="workflow-steps" aria-label="Assessment workflow">
      <span class="step complete">1. Details</span>
      <span class="step complete">2. Scope</span>
      <span class="step complete">3. Import</span>
      <span class="step complete">4. Validation</span>
      <span class="step complete">5. Review</span>
      <span class="step active">6. Confirmation</span>
      <span class="step">7. Results Ledger</span>
    </nav>

    <article class="confirmation-card">
      <div class="success-icon" aria-hidden="true">✓</div>

      <p class="eyebrow">Assessment workflow · Submission complete</p>
      <h2>Assessment submitted successfully</h2>

      <p class="description">
        The assessment and its results have been submitted successfully.
        Submitted assessment data is now immutable.
      </p>

      <span class="submitted-pill">Submitted</span>

      <div class="details-grid">
        <div>
          <span>Assessment name</span>
          <strong>{{ assessment.name }}</strong>
        </div>
        <div>
          <span>Assessment type</span>
          <strong>{{ assessment.assessment_type }}</strong>
        </div>
        <div>
          <span>Sequence</span>
          <strong>{{ assessment.sequence_no }}</strong>
        </div>
        <div>
          <span>Maximum marks</span>
          <strong>{{ assessment.maximum_marks }}</strong>
        </div>
        <div>
          <span>Assessment date</span>
          <strong>{{ assessment.assessment_date || 'Not specified' }}</strong>
        </div>
        <div>
          <span>Submission status</span>
          <strong>{{ assessment.status }}</strong>
        </div>
      </div>

      <div class="immutability-note">
        <strong>Important</strong>
        <p>
          Submitted results cannot be edited or resubmitted. You can review
          the recorded student results in the Results Ledger.
        </p>
      </div>

      <div class="actions">
        <button
          class="button button-secondary"
          type="button"
          @click="emit('backToDirectory')"
        >
          Back to Assessment Directory
        </button>

        <button
          class="button button-primary"
          type="button"
          @click="emit('viewResults')"
        >
          View Results Ledger
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.submission-confirmation {
  display: flex;
  flex-direction: column;
  gap: 24px;
  color: var(--text-primary, #18352d);
}

.workflow-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.step {
  padding: 9px 13px;
  border-radius: 8px;
  background: var(--surface-muted, #f1f4f1);
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.step.complete {
  background: #e5f2e9;
  color: #23623d;
}

.step.active {
  background: #173e32;
  color: #fff;
}

.confirmation-card {
  max-width: 850px;
  margin: 0 auto;
  padding: 32px;
  border: 1px solid var(--border-color, #dce5df);
  border-radius: 14px;
  background: var(--surface-card, #fff);
  text-align: center;
}

.success-icon {
  display: grid;
  width: 58px;
  height: 58px;
  margin: 0 auto 18px;
  place-items: center;
  border-radius: 50%;
  background: #e5f2e9;
  color: #23623d;
  font-size: 32px;
  font-weight: 700;
}

.eyebrow {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.confirmation-card h2 {
  margin: 8px 0;
  font-size: 25px;
}

.description {
  max-width: 580px;
  margin: 0 auto 18px;
  color: var(--text-secondary, #687b73);
  font-size: 14px;
  line-height: 1.6;
}

.submitted-pill {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 20px;
  background: #e5f2e9;
  color: #23623d;
  font-size: 12px;
  font-weight: 700;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  margin-top: 28px;
  padding: 22px;
  border-radius: 10px;
  background: var(--surface-muted, #f1f4f1);
  text-align: left;
}

.details-grid > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.details-grid span {
  color: var(--text-secondary, #687b73);
  font-size: 12px;
}

.details-grid strong {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.immutability-note {
  margin-top: 20px;
  padding: 15px;
  border-radius: 9px;
  background: #fff3dc;
  color: #805819;
  text-align: left;
}

.immutability-note p {
  margin: 5px 0 0;
  font-size: 13px;
  line-height: 1.5;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  margin-top: 25px;
}

.button {
  min-height: 40px;
  padding: 9px 16px;
  border: 1px solid transparent;
  border-radius: 7px;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
}

.button-primary {
  background: #173e32;
  color: #fff;
}

.button-secondary {
  border-color: var(--border-color, #ccd8d0);
  background: var(--surface-card, #fff);
  color: inherit;
}

@media (max-width: 700px) {
  .confirmation-card {
    padding: 20px;
  }

  .details-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .actions {
    flex-direction: column-reverse;
  }

  .actions .button {
    width: 100%;
  }
}
</style>
