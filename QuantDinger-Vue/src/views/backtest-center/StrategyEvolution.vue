<template>
  <div class="evolution-shell" :class="{ 'theme-dark': isDarkTheme }" data-testid="strategy-evolution">
    <aside class="evolution-rail evolution-config">
      <div class="evolution-scroll">
        <section class="evolution-section">
          <div class="evolution-section__heading">
            <div><span class="step-badge">1</span><h3>{{ $t('strategyEvolution.strategySetup') }}</h3></div>
          </div>
          <a-select
            v-model="form.sourceId"
            show-search
            option-filter-prop="children"
            class="full-width"
            :loading="loadingSources"
            @change="selectSource">
            <a-select-option v-for="item in sources" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
          </a-select>
        </section>
        <section class="evolution-section">
          <div class="evolution-section__heading">
            <div><span class="step-badge">2</span><h3>{{ $t('strategyEvolution.parameterSpace') }}</h3></div>
            <span>{{ selectedParameterCount }}/{{ searchableParameterCount }}</span>
          </div>
          <div v-if="parameterDefinitions.length" class="parameter-space-hint">
            <a-icon type="robot" />
            <span>{{ $t('strategyEvolution.systemSampling') }}</span>
          </div>
          <a-alert
            v-if="parameterContract && parameterContract.scope === 'riskExecution'"
            class="parameter-scope-alert"
            type="info"
            show-icon
            :message="$t('strategyEvolution.robotScopeHint')" />
          <div v-if="!parameterDefinitions.length" class="evolution-muted">{{ $t('strategyEvolution.noParameters') }}</div>
          <div v-for="item in parameterDefinitions" :key="item.name" class="parameter-row" :class="{ 'parameter-row--disabled': !searchableParameter(item) }">
            <div class="parameter-row__title">
              <a-checkbox :checked="parameterEnabled[item.name]" :disabled="!searchableParameter(item)" @change="toggleParameter(item.name, $event.target.checked)">{{ parameterLabel(item) }}</a-checkbox>
              <code>{{ item.name }}</code>
            </div>
            <div v-if="parameterEnabled[item.name]" class="parameter-domain">
              <template v-if="numericParameter(item)">
                <label>
                  <span>{{ $t('strategyEvolution.parameterMin') }}</span>
                  <a-input-number
                    :value="parameterSpace[item.name].min"
                    :min="item.min"
                    :max="parameterSpace[item.name].max"
                    :step="parameterStepIncrement(item)"
                    @change="updateParameterRange(item.name, 'min', $event)" />
                </label>
                <label>
                  <span>{{ $t('strategyEvolution.parameterMax') }}</span>
                  <a-input-number
                    :value="parameterSpace[item.name].max"
                    :min="parameterSpace[item.name].min"
                    :max="item.max"
                    :step="parameterStepIncrement(item)"
                    @change="updateParameterRange(item.name, 'max', $event)" />
                </label>
                <label>
                  <span>{{ $t('strategyEvolution.parameterStep') }}</span>
                  <a-input-number
                    :value="parameterSpace[item.name].step"
                    :min="parameterStepMinimum(item)"
                    :max="parameterStepMaximum(item)"
                    :step="parameterStepIncrement(item)"
                    @change="updateParameterRange(item.name, 'step', $event)" />
                </label>
                <div class="parameter-domain__footer">
                  <small>{{ $t('strategyEvolution.parameterDomainSummary', { min: formatParameterValue(item.min), max: formatParameterValue(item.max), count: parameterDomainSize(item) }) }}</small>
                  <a-button type="link" size="small" @click="resetParameterRange(item)">{{ $t('strategyEvolution.resetRecommended') }}</a-button>
                </div>
              </template>
              <template v-else-if="booleanParameter(item)">
                <span>{{ $t('strategyEvolution.boolean.false') }}</span><i>/</i><span>{{ $t('strategyEvolution.boolean.true') }}</span>
              </template>
              <template v-else>
                <span>{{ parameterChoices(item).join(' / ') }}</span>
              </template>
            </div>
          </div>
        </section>
        <section class="evolution-section">
          <div class="evolution-section__heading">
            <div><span class="step-badge">3</span><h3>{{ $t('strategyEvolution.searchSetup') }}</h3></div>
          </div>
          <label class="field-label">{{ $t('strategyEvolution.searchMethod') }}</label>
          <div class="method-grid">
            <button
              v-for="method in searchMethods"
              :key="method.value"
              type="button"
              class="method-card"
              :class="{ 'method-card--active': form.method === method.value }"
              @click="selectSearchMethod(method.value)">
              <a-icon :type="method.icon" />
              <span><strong>{{ $t(`strategyEvolution.method.${method.value}`) }}</strong><small>{{ $t(`strategyEvolution.methodHint.${method.value}`) }}</small></span>
            </button>
          </div>
          <div class="budget-presets">
            <button
              v-for="preset in budgetPresets"
              :key="preset.value"
              type="button"
              :class="{ active: form.trials === preset.trials && form.folds === preset.folds }"
              @click="applyBudgetPreset(preset)">
              <strong>{{ $t(`strategyEvolution.budget.${preset.value}`) }}</strong>
              <small>{{ $t(`strategyEvolution.budgetHint.${preset.value}`, { trials: preset.trials, effective: effectivePresetTrials(preset), folds: preset.folds }) }}</small>
            </button>
          </div>
          <div class="two-col">
            <a-form-item :label="$t('strategyEvolution.trials')"><a-input-number v-model="form.trials" :min="trialMinimum" :max="trialMaximum" /></a-form-item>
            <a-form-item :label="$t('strategyEvolution.folds')"><a-input-number v-model="form.folds" :min="4" :max="10" /></a-form-item>
          </div>
          <p class="effective-budget">{{ $t('strategyEvolution.effectiveBudget', { effective: estimatedTrials, requested: form.trials }) }}</p>
          <a-alert
            v-if="estimate && !estimate.sampleSufficient"
            class="sample-alert"
            type="warning"
            show-icon
            :message="$t('strategyEvolution.sampleInsufficient', { trials: estimate.trials, minimum: estimate.minimumRecommendedTrials })" />
          <div class="two-col">
            <a-form-item :label="$t('strategyEvolution.trainRatio')"><a-input-number v-model="form.trainRatio" :min="0.55" :max="0.85" :step="0.05" /></a-form-item>
            <a-form-item :label="$t('strategyEvolution.blindRatio')"><a-input-number v-model="form.blindRatio" :min="0" :max="0.3" :step="0.05" /></a-form-item>
          </div>
          <div class="switch-setting"><span>{{ $t('strategyEvolution.autoPrune') }}</span><a-switch v-model="form.autoPrune" /></div>
        </section>
        <section class="evolution-section">
          <div class="evolution-section__heading">
            <div><span class="step-badge">4</span><h3>{{ $t('strategyEvolution.dateRange') }}</h3></div>
          </div>
          <div class="date-presets">
            <a-button
              v-for="preset in datePresets"
              :key="preset.key"
              size="small"
              :type="preset.active ? 'primary' : 'default'"
              :disabled="preset.disabled"
              :aria-pressed="preset.active ? 'true' : 'false'"
              @click="applyDatePreset(preset)">
              {{ preset.label }}
            </a-button>
          </div>
          <div class="date-range-fields">
            <label><span>{{ $t('strategyEvolution.startDate') }}</span><a-date-picker v-model="form.startDate" class="full-width" /></label>
            <a-icon type="arrow-right" />
            <label><span>{{ $t('strategyEvolution.endDate') }}</span><a-date-picker v-model="form.endDate" class="full-width" /></label>
          </div>
          <div class="two-col">
            <a-form-item :label="$t('strategyEvolution.commission')"><a-input-number v-model="form.commission" :min="0" :max="1" :step="0.0001" /></a-form-item>
            <a-form-item :label="$t('strategyEvolution.slippage')"><a-input-number v-model="form.slippage" :min="0" :max="1" :step="0.0001" /></a-form-item>
          </div>
        </section>
      </div>
      <div class="evolution-runbar">
        <div class="resource-estimate"><span>{{ $t('strategyEvolution.estimatedTrials') }}</span><strong>{{ estimatedTrials }}</strong></div>
        <div class="resource-estimate resource-estimate--runs"><span>{{ $t('strategyEvolution.estimatedRuns') }}</span><strong>{{ estimatedRuns }}</strong></div>
        <div class="resource-estimate"><span>{{ $t('strategyEvolution.searchSpaceSize') }}</span><strong>{{ searchSpaceSize }}</strong></div>
        <div class="resource-estimate"><span>{{ $t('strategyEvolution.searchCoverage') }}</span><strong>{{ searchCoverage }}</strong></div>
        <p class="estimate-hint">{{ $t(estimateIsUpperBound ? 'strategyEvolution.estimateUpperBound' : 'strategyEvolution.estimateExact') }}</p>
        <div v-if="running" class="run-actions">
          <a-button icon="stop" @click="cancelStudy">{{ $t('strategyEvolution.cancel') }}</a-button>
          <a-button type="primary" block size="large" icon="loading" disabled>{{ progressLabel }}</a-button>
        </div>
        <a-button
          v-else
          type="primary"
          block
          size="large"
          icon="thunderbolt"
          :disabled="!canRun"
          @click="runStudy">
          {{ $t('strategyEvolution.run') }}
        </a-button>
      </div>
    </aside>

    <main class="evolution-main">
      <div v-if="!result && !running && progress.phase === 'failed'" class="evolution-empty evolution-failure">
        <span class="empty-icon"><a-icon type="warning" /></span>
        <h2>{{ $t('strategyEvolution.failureTitle') }}</h2>
        <p>{{ jobFailureMessage({ progress }) }}</p>
        <div v-if="progress.failure" class="failure-facts">
          <span><b>{{ progress.failure.totalTrials || 0 }}</b>{{ $t('strategyEvolution.failure.candidates') }}</span>
          <span><b>{{ progress.failure.activeTrainingTrials || 0 }}</b>{{ $t('strategyEvolution.failure.trainingActive') }}</span>
          <span><b>{{ progress.failure.activeValidationTrials || 0 }}</b>{{ $t('strategyEvolution.failure.validationActive') }}</span>
          <span v-if="progress.failure.actualBacktestRuns !== null && progress.failure.actualBacktestRuns !== undefined"><b>{{ progress.failure.actualBacktestRuns }}</b>{{ $t('strategyEvolution.actualRuns') }}</span>
        </div>
      </div>
      <div v-else-if="!result && !running" class="evolution-empty evolution-empty--setup">
        <span class="empty-icon"><a-icon type="experiment" /></span>
        <h2>{{ $t('strategyEvolution.emptyTitle') }}</h2>
        <p>{{ $t('strategyEvolution.emptyHint') }}</p>
        <div class="empty-flow">
          <span>{{ $t('strategyEvolution.flow.search') }}</span><a-icon type="arrow-right" />
          <span>{{ $t('strategyEvolution.flow.walkForward') }}</span><a-icon type="arrow-right" />
          <span>{{ $t('strategyEvolution.flow.robustness') }}</span>
        </div>
      </div>
      <div v-else-if="running" class="evolution-empty">
        <a-icon type="loading" class="running-spinner" />
        <h2>{{ $t('strategyEvolution.runningTitle') }}</h2>
        <p>{{ $t('strategyEvolution.runningHint', { trials: estimatedTrials, runs: estimatedRuns }) }}</p>
        <a-progress :percent="progressPercent" class="evolution-progress" />
      </div>
      <template v-else>
        <header class="result-header">
          <div><span class="eyebrow">{{ $t('strategyEvolution.completed') }}</span><h2>{{ result.source.name }}</h2></div>
          <a-button :type="recommendBest ? 'primary' : 'default'" :icon="recommendBest ? 'check' : 'experiment'" @click="applyBestParams">{{ $t(recommendBest ? 'strategyEvolution.applyBest' : 'strategyEvolution.applyForReview') }}</a-button>
        </header>
        <section class="research-verdict" :class="{ 'research-verdict--review': !recommendBest }">
          <div class="research-verdict__icon"><a-icon :type="recommendBest ? 'check' : 'warning'" /></div>
          <div class="research-verdict__copy">
            <span>{{ $t('strategyEvolution.verdictLabel') }}</span>
            <strong>{{ $t(recommendBest ? 'strategyEvolution.decision.readyTitle' : 'strategyEvolution.decision.reviewTitle') }}</strong>
            <p>{{ $t(deploymentReasonKey, deploymentReasonValues) }}</p>
          </div>
          <div class="research-verdict__chips">
            <span class="verdict-chip verdict-chip--status"><i />{{ $t(recommendBest ? 'strategyEvolution.decision.ready' : 'strategyEvolution.decision.review') }}</span>
            <span
              v-if="boundaryConvergence.length"
              class="verdict-chip verdict-chip--boundary"
              :title="$t('strategyEvolution.boundaryHint', { parameters: boundaryConvergence.join(' · ') })">
              <a-icon type="vertical-align-middle" />{{ $t('strategyEvolution.boundaryTag', { parameters: boundaryConvergence.join(' · ') }) }}
            </span>
          </div>
        </section>
        <div class="study-facts">
          <span v-if="result.plan && result.plan.sampleCount"><b>{{ result.plan.sampleCount }}</b>{{ $t('strategyEvolution.marketBars') }}</span>
          <span v-if="result.plan && result.plan.effectiveFolds"><b>{{ result.plan.effectiveFolds }}</b>{{ $t('strategyEvolution.effectiveFolds') }}</span>
          <span v-if="result.plan && result.plan.blindBars"><b>{{ result.plan.blindBars }}</b>{{ $t('strategyEvolution.blindBars') }}</span>
          <span><b>{{ result.summary.evaluatedTrials || result.summary.completedTrials }}</b>{{ $t('strategyEvolution.evaluatedTrials') }}</span>
          <span v-if="resultCandidateAttempts"><b>{{ resultCandidateAttempts }}</b>{{ $t('strategyEvolution.candidateAttempts') }}</span>
          <span v-if="result.summary.constraintRejectedTrials"><b>{{ result.summary.constraintRejectedTrials }}</b>{{ $t('strategyEvolution.constraintRejectedTrials') }}</span>
          <span v-if="result.summary.overfitRejectedTrials"><b>{{ result.summary.overfitRejectedTrials }}</b>{{ $t('strategyEvolution.overfitRejectedTrials') }}</span>
          <span v-if="result.summary.duplicateTrials"><b>{{ result.summary.duplicateTrials }}</b>{{ $t('strategyEvolution.duplicateTrials') }}</span>
          <span v-if="result.summary.actualBacktestRuns !== null && result.summary.actualBacktestRuns !== undefined"><b>{{ result.summary.actualBacktestRuns }}</b>{{ $t('strategyEvolution.actualRuns') }}</span>
          <span v-if="result.summary.elapsedSeconds !== null && result.summary.elapsedSeconds !== undefined"><b>{{ formatDuration(result.summary.elapsedSeconds) }}</b>{{ $t('strategyEvolution.elapsed') }}</span>
        </div>
        <div class="metric-grid">
          <article><span>{{ $t('strategyEvolution.robustnessScore') }}</span><strong>{{ result.summary.robustnessScore }}</strong><em>{{ result.summary.robustnessGrade }}</em></article>
          <article><span>{{ $t('strategyEvolution.oosReturn') }}</span><strong>{{ formatPercent(result.summary.oosReturn) }}</strong></article>
          <article><span>{{ $t('strategyEvolution.oosSharpe') }}</span><strong>{{ formatNumber(result.summary.oosSharpe) }}</strong></article>
          <article><span>{{ $t('strategyEvolution.maxDrawdown') }}</span><strong class="negative">-{{ formatPercent(result.summary.maxDrawdown) }}</strong></article>
          <article><span>{{ $t('strategyEvolution.decay') }}</span><strong>{{ formatPercent(result.summary.decayRate) }}</strong></article>
          <article><span>{{ $t('strategyEvolution.blindReturn') }}</span><strong :class="{ negative: Number(result.summary.blindReturn) < 0 }">{{ result.summary.blindReturn === null || result.summary.blindReturn === undefined ? '—' : formatPercent(result.summary.blindReturn) }}</strong><em>{{ $t(result.summary.blindPassed ? 'strategyEvolution.blindPassed' : 'strategyEvolution.blindFailed') }}</em></article>
        </div>
        <div class="chart-grid chart-grid--hero">
          <section class="chart-card chart-card--wide"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.equity') }}</strong><span>{{ $t('strategyEvolution.chart.blindHint') }}</span></div><div ref="equityChart" class="chart chart--hero" /></section>
          <section class="chart-card"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.drawdown') }}</strong></div><div ref="drawdownChart" class="chart chart--hero" /></section>
        </div>
        <div class="chart-grid">
          <section class="chart-card"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.convergence') }}</strong></div><div ref="convergenceChart" class="chart" /></section>
          <section class="chart-card"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.heatmap') }}</strong></div><div ref="heatmapChart" class="chart" /></section>
          <section class="chart-card"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.monteCarlo') }}</strong><span>{{ $t('strategyEvolution.chart.monteCarloHint') }}</span></div><div ref="monteCarloChart" class="chart" /></section>
          <section class="chart-card"><div class="chart-title"><strong>{{ $t('strategyEvolution.chart.costStress') }}</strong><span>{{ $t('strategyEvolution.chart.costStressHint') }}</span></div><div ref="costChart" class="chart" /></section>
        </div>
        <section v-if="bestCandidate && bestCandidate.folds && bestCandidate.folds.length" class="candidate-card fold-card">
          <div class="chart-title"><strong>{{ $t('strategyEvolution.segmentValidation') }}</strong><span>{{ $t('strategyEvolution.segmentValidationHint') }}</span></div>
          <div class="fold-table">
            <div class="fold-table__head"><span>{{ $t('strategyEvolution.fold') }}</span><span>{{ $t('strategyEvolution.trainingRange') }}</span><span>{{ $t('strategyEvolution.validationRange') }}</span><span>{{ $t('strategyEvolution.trainingReturn') }}</span><span>{{ $t('strategyEvolution.validationReturn') }}</span><span>{{ $t('strategyEvolution.validationActivity') }}</span></div>
            <div v-for="fold in bestCandidate.folds" :key="fold.index" class="fold-table__row">
              <strong>#{{ fold.index }}</strong><span>{{ formatFoldRange(fold.trainStart, fold.trainEnd) }}</span><span>{{ formatFoldRange(fold.validationStart, fold.validationEnd) }}</span><span>{{ formatPercent(fold.train.return) }}</span><span :class="{ negative: Number(fold.validation.return) < 0 }">{{ formatPercent(fold.validation.return) }}</span><span>{{ formatNumber(fold.validation.activity) }}</span>
            </div>
          </div>
        </section>
        <section class="candidate-card">
          <div class="chart-title"><strong>{{ $t('strategyEvolution.topCandidates') }}</strong><span>{{ result.summary.completedTrials }} · {{ $t('strategyEvolution.completedTrials') }}</span></div>
          <div class="candidate-table">
            <div class="candidate-table__head"><span>#</span><span>{{ $t('strategyEvolution.rankingReturn') }}</span><span>{{ $t('strategyEvolution.parameters') }}</span><span>{{ $t('strategyEvolution.validationActivity') }}</span><span>{{ $t('strategyEvolution.profitableFolds') }}</span><span>{{ $t('strategyEvolution.maxDrawdown') }}</span></div>
            <div v-for="item in result.topCandidates" :key="item.number" class="candidate-table__row">
              <span>{{ item.number }}</span><strong>{{ formatPercent(item.score) }}</strong><code>{{ formatParams(item.params) }}</code><span>{{ formatNumber(item.components.validationActivity) }}</span><span>{{ item.components.positiveValidationFolds }}/{{ item.components.validationFolds }}</span><span>{{ formatPercent(item.components.maxDrawdown) }}</span>
            </div>
          </div>
        </section>
      </template>
    </main>

    <aside class="evolution-rail evolution-validation">
      <div class="evolution-rail__title history-title">
        <a-icon type="history" />
        <div><strong>{{ $t('strategyEvolution.historyTitle') }}</strong><span>{{ $t('strategyEvolution.historyHint') }}</span></div>
        <a-button type="link" icon="reload" :loading="historyLoading" @click="loadHistory" />
      </div>
      <div class="history-list">
        <div v-if="!history.length && !historyLoading" class="history-empty">{{ $t('strategyEvolution.historyEmpty') }}</div>
        <button
          v-for="job in history"
          :key="job.jobId"
          type="button"
          class="history-item"
          :class="{ 'history-item--active': job.jobId === jobId }"
          @click="openHistory(job)">
          <span class="history-item__top"><strong>{{ historySourceName(job) }}</strong><em :class="`job-status job-status--${job.status}`">{{ $t(`strategyEvolution.status.${job.status}`) }}</em></span>
          <span>{{ historyMethod(job) }} · {{ historyDateRange(job) }}</span>
          <small v-if="job.status === 'failed'" class="history-item__failure" :title="jobFailureMessage(job)">{{ jobFailureMessage(job) }}</small>
          <small>{{ formatDateTime(job.createdAt) }}</small>
        </button>
      </div>
      <div class="validation-divider"><a-icon type="safety-certificate" /><strong>{{ $t('strategyEvolution.validationTitle') }}</strong></div>
      <div class="validation-scroll">
        <template v-if="result">
          <article class="deployment-decision" :class="{ 'deployment-decision--review': !recommendBest }">
            <span><a-icon :type="recommendBest ? 'check-circle' : 'warning'" />{{ $t(recommendBest ? 'strategyEvolution.decision.ready' : 'strategyEvolution.decision.review') }}</span>
            <strong>{{ $t(recommendBest ? 'strategyEvolution.decision.readyTitle' : 'strategyEvolution.decision.reviewTitle') }}</strong>
            <p>{{ $t(deploymentReasonKey, deploymentReasonValues) }}</p>
          </article>
          <div class="validation-score" :class="`validation-score--${String(result.summary.robustnessGrade || 'D').toLowerCase()}`">
            <span>{{ result.summary.robustnessGrade }}</span>
            <div><strong>{{ result.summary.robustnessScore }}<small>/100</small></strong><p>{{ $t('strategyEvolution.robustnessCoverage', { available: robustnessAvailableChecks, total: robustnessTotalChecks }) }}</p></div>
          </div>
          <article class="validation-card"><div><a-icon type="experiment" /><strong>{{ $t('strategyEvolution.pbo') }}</strong></div><b>{{ result.validation.pbo.available ? formatPercent(result.validation.pbo.probability * 100) : '—' }}</b><p v-if="result.validation.pbo.available">{{ $t('strategyEvolution.pboDetail', { reversals: pboReversals, samples: result.validation.pbo.samples }) }}</p><p v-else>{{ $t('strategyEvolution.validationInsufficient') }}</p></article>
          <article class="validation-card"><div><a-icon type="rise" /><strong>{{ $t('strategyEvolution.dsr') }}</strong></div><b>{{ result.validation.deflatedSharpe.available ? formatPercent(result.validation.deflatedSharpe.probability * 100) : '—' }}</b><p v-if="deflatedSharpeHasDetails">{{ $t('strategyEvolution.dsrDetail', { observed: formatNumber(result.validation.deflatedSharpe.observedSharpe), benchmark: formatNumber(result.validation.deflatedSharpe.benchmarkSharpe), observations: result.validation.deflatedSharpe.observations }) }}</p><p v-else>{{ $t(result.validation.deflatedSharpe.available ? 'strategyEvolution.dsrHint' : 'strategyEvolution.validationInsufficient') }}</p></article>
          <article class="validation-card"><div><a-icon type="cluster" /><strong>{{ $t('strategyEvolution.monteCarlo') }}</strong></div><b>{{ monteCarloAvailable ? formatPercent(monteCarloMedian) : '—' }}</b><p v-if="monteCarloHasDetails">{{ $t('strategyEvolution.monteCarloDetail', { loss: formatPercent(result.validation.monteCarlo.lossProbability * 100), paths: result.validation.monteCarlo.paths, observations: result.validation.monteCarlo.observations }) }}</p><p v-else>{{ $t(monteCarloAvailable ? 'strategyEvolution.monteCarloHint' : 'strategyEvolution.validationInsufficient') }}</p></article>
          <article class="validation-card"><div><a-icon type="dollar" /><strong>{{ $t('strategyEvolution.costStress') }}</strong></div><b>{{ worstCostStress ? formatPercent(worstCostStress.return) : '—' }}</b><p v-if="worstCostStress">{{ $t('strategyEvolution.costStressDetail', { multiplier: worstCostStress.multiplier, delta: formatPercent(worstCostStressDelta) }) }}</p><p v-else>{{ $t('strategyEvolution.validationInsufficient') }}</p></article>
          <section class="best-params"><strong>{{ $t('strategyEvolution.bestParams') }}</strong><div v-for="(value, key) in result.bestParams" :key="key"><code>{{ key }}</code><b>{{ value }}</b></div></section>
        </template>
        <div v-else class="validation-placeholder"><a-icon type="safety-certificate" /><p>{{ $t('strategyEvolution.validationEmpty') }}</p></div>
      </div>
    </aside>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import moment from 'moment'
import { mapState } from 'vuex'
import { cancelStrategyEvolutionJob, compileScriptSource, estimateStrategyEvolution, getScriptSourceList, getScriptSourceDetail, getStrategyEvolutionJob, getStrategyEvolutionJobs, getStrategyEvolutionParameterSpace, runStrategyEvolution } from '@/api/strategy'
import { strategyParameterLabel } from '@/utils/strategyParameterPresentation'

export default {
  name: 'StrategyEvolution',
  data () {
    const end = moment().subtract(1, 'day').startOf('day')
    return {
      sources: [],
      loadingSources: false,
      loadingSource: false,
      source: null,
      manifest: null,
      backtestRangePolicy: null,
      parameterDefinitions: [],
      parameterContract: null,
      parameterEnabled: {},
      parameterSpace: {},
      running: false,
      jobId: '',
      progress: {},
      pollTimer: null,
      result: null,
      charts: [],
      estimate: null,
      estimateLoading: false,
      estimateTimer: null,
      estimateRequestId: 0,
      history: [],
      historyLoading: false,
      historyRequestId: 0,
      searchMethods: [
        { value: 'random', icon: 'swap' },
        { value: 'grid', icon: 'appstore' },
        { value: 'tpe', icon: 'deployment-unit' }
      ],
      budgetPresets: [
        { value: 'quick', trials: 32, folds: 4 },
        { value: 'standard', trials: 64, folds: 5 },
        { value: 'deep', trials: 160, folds: 6 }
      ],
      form: { sourceId: null, method: 'tpe', trials: 64, folds: 5, trainRatio: 0.7, blindRatio: 0.15, autoPrune: false, startDate: end.clone().subtract(2, 'years'), endDate: end, commission: 0.0005, slippage: 0.0005 }
    }
  },
  computed: {
    ...mapState({
      navTheme: state => state.app.theme,
      primaryColor: state => state.app.color || '#52C41A'
    }),
    isDarkTheme () { return this.navTheme === 'dark' || this.navTheme === 'realdark' },
    selectedParameterCount () { return Object.values(this.parameterEnabled).filter(Boolean).length },
    searchableParameterCount () { return this.parameterDefinitions.filter(this.searchableParameter).length },
    estimatedRuns () { return this.estimatedTrials + 4 },
    estimatedTrials () { return this.effectiveTrialCount },
    trialMinimum () { return this.form.method === 'tpe' ? 32 : 1 },
    trialMaximum () { return this.form.method === 'grid' ? 5000 : 500 },
    localSearchSpaceSize () {
      if (!this.selectedParameterCount || !this.parameterRangesValid) return 0
      return this.parameterDefinitions.reduce((size, item) => {
        if (!this.parameterEnabled[item.name]) return size
        return Math.min(10000000, size * this.parameterDomainSize(item))
      }, 1)
    },
    effectiveTrialCount () {
      const requested = Math.max(1, Number(this.form.trials) || 1)
      return this.localSearchSpaceSize > 0 ? Math.min(requested, this.localSearchSpaceSize) : requested
    },
    searchSpaceSize () {
      const value = Number(this.localSearchSpaceSize)
      return Number.isFinite(value) && value > 0 ? value.toLocaleString() : '—'
    },
    searchCoverage () {
      const value = this.localSearchSpaceSize > 0 ? (this.effectiveTrialCount / this.localSearchSpaceSize) * 100 : NaN
      if (!Number.isFinite(value)) return '—'
      if (value > 0 && value < 0.01) return '<0.01%'
      return `${value.toFixed(value >= 10 ? 1 : 2)}%`
    },
    estimateIsUpperBound () { return Boolean(this.form.autoPrune || (this.estimate && this.estimate.isUpperBound)) },
    progressPercent () { return this.progress.total ? Math.round((Number(this.progress.completed || 0) / Number(this.progress.total)) * 100) : 0 },
    progressLabel () { return this.progress.total ? `${this.progress.completed || 0}/${this.progress.total}` : this.$t('strategyEvolution.running') },
    manifestFrequency () {
      const subscriptions = (this.manifest && this.manifest.subscriptions) || []
      return (this.manifest && this.manifest.primaryFrequency) || (subscriptions[0] && subscriptions[0].frequency) || '-'
    },
    backtestRangeLimitDays () {
      if (!this.backtestRangePolicy || this.backtestRangePolicy.maxSelectedDays === null || this.backtestRangePolicy.maxSelectedDays === undefined) return null
      const value = Number(this.backtestRangePolicy.maxSelectedDays)
      return Number.isFinite(value) ? Math.max(0, value) : null
    },
    selectedRangeDays () {
      if (!this.form.startDate || !this.form.endDate) return null
      return this.form.endDate.clone().startOf('day').diff(this.form.startDate.clone().startOf('day'), 'days')
    },
    backtestRangeExceeded () {
      if (this.selectedRangeDays === null || this.selectedRangeDays < 0) return true
      return this.backtestRangeLimitDays !== null && this.selectedRangeDays > this.backtestRangeLimitDays
    },
    parameterRangesValid () {
      return this.parameterDefinitions.every(item => {
        if (!this.parameterEnabled[item.name] || !this.numericParameter(item)) return true
        const range = this.parameterSpace[item.name] || {}
        const minimum = Number(range.min); const maximum = Number(range.max); const step = Number(range.step)
        const integerStepValid = !['int', 'integer'].includes(item.type) || Number.isInteger(step)
        return Number.isFinite(minimum) && Number.isFinite(maximum) && Number.isFinite(step) && minimum <= maximum && minimum >= Number(item.min) && maximum <= Number(item.max) && step > 0 && integerStepValid && (minimum === maximum || step <= maximum - minimum)
      })
    },
    robustnessAvailableChecks () { return Number((((this.result || {}).summary || {}).availableChecks) || this.inferAvailableChecks()) },
    robustnessTotalChecks () { return Number((((this.result || {}).summary || {}).totalChecks) || 4) },
    deflatedSharpeHasDetails () {
      const row = (((this.result || {}).validation || {}).deflatedSharpe || {})
      return Boolean(row.available && row.observedSharpe !== undefined && row.observations !== undefined)
    },
    monteCarloAvailable () { return Boolean(this.result && this.result.validation && this.result.validation.monteCarlo && this.result.validation.monteCarlo.available) },
    monteCarloHasDetails () {
      const row = (((this.result || {}).validation || {}).monteCarlo || {})
      return Boolean(row.available && row.observations !== undefined)
    },
    monteCarloMedian () { return Number(((((this.result || {}).validation || {}).monteCarlo || {}).percentiles || {})['50'] || 0) },
    worstCostStress () {
      const rows = (((this.result || {}).validation || {}).costStress || [])
      return rows.length ? rows[rows.length - 1] : null
    },
    worstCostStressDelta () {
      const rows = (((this.result || {}).validation || {}).costStress || [])
      if (!rows.length) return 0
      const worst = rows[rows.length - 1]
      return worst.returnDelta !== undefined ? Number(worst.returnDelta) : Number(worst.return || 0) - Number(rows[0].return || 0)
    },
    bestCandidate () { return this.result && this.result.topCandidates && this.result.topCandidates[0] },
    resultCandidateAttempts () {
      const summary = (this.result && this.result.summary) || {}
      const evaluated = Number(summary.evaluatedTrials || summary.completedTrials || 0)
      const rejected = Number(summary.constraintRejectedTrials || 0) + Number(summary.duplicateTrials || 0)
      return Math.max(Number(summary.candidateAttempts || 0), evaluated + rejected)
    },
    pboReversals () {
      const pbo = this.result && this.result.validation && this.result.validation.pbo
      return pbo && Array.isArray(pbo.logits) ? pbo.logits.filter(value => Number(value) <= 0).length : 0
    },
    boundaryConvergence () {
      const rows = (this.result && this.result.topCandidates) || []
      if (rows.length < 3) return []
      return this.parameterDefinitions.filter(item => this.numericParameter(item) && this.parameterEnabled[item.name]).reduce((output, item) => {
        const range = this.parameterSpace[item.name] || {}
        const values = rows.map(row => Number((row.params || {})[item.name])).filter(Number.isFinite)
        if (values.length !== rows.length) return output
        const minimum = Number(range.min); const maximum = Number(range.max)
        const atMinimum = Number.isFinite(minimum) && values.every(value => value === minimum)
        const atMaximum = Number.isFinite(maximum) && values.every(value => value === maximum)
        if (atMinimum || atMaximum) output.push(`${item.name}=${this.formatParameterValue(atMinimum ? minimum : maximum)}`)
        return output
      }, [])
    },
    resultSampleSufficient () {
      if (!this.result || !this.result.summary) return false
      const summary = this.result.summary
      if (summary.sampleSufficient !== undefined) return Boolean(summary.sampleSufficient)
      return Number(summary.evaluatedTrials || summary.completedTrials || 0) >= 32
    },
    recommendBest () {
      if (!this.result || !this.result.summary) return false
      if (!this.resultSampleSufficient) return false
      if (this.result.summary.recommended !== undefined) return Boolean(this.result.summary.recommended)
      const blindReturn = this.result.summary.blindReturn
      return Number(this.result.summary.oosReturn) > 0 && (blindReturn === null || blindReturn === undefined || Boolean(this.result.summary.blindPassed))
    },
    deploymentReasonKey () {
      if (!this.result || !this.result.summary) return 'strategyEvolution.decision.reviewGeneric'
      const summary = this.result.summary
      if (!this.resultSampleSufficient) return 'strategyEvolution.decision.insufficientSample'
      if (Number(summary.oosReturn) <= 0) return 'strategyEvolution.decision.negativeValidation'
      if (summary.blindReturn !== null && summary.blindReturn !== undefined && !summary.blindPassed) return 'strategyEvolution.decision.blindFailed'
      if (Number(summary.positiveValidationFolds || 0) < Math.ceil(Number(summary.validationFolds || 0) / 2)) return 'strategyEvolution.decision.unstableSegments'
      return this.recommendBest ? 'strategyEvolution.decision.readyReason' : 'strategyEvolution.decision.reviewGeneric'
    },
    deploymentReasonValues () {
      const summary = (this.result && this.result.summary) || {}
      const estimate = this.estimate || {}
      const evaluated = Number(summary.evaluatedTrials || summary.completedTrials || 0)
      const space = Number(summary.searchSpaceSize || estimate.searchSpaceSize || 0)
      const minimum = Number(summary.minimumRecommendedTrials || estimate.minimumRecommendedTrials || 32)
      const coverage = summary.coveragePercent !== undefined
        ? Number(summary.coveragePercent)
        : (space > 0 ? (evaluated / space) * 100 : 0)
      return {
        positive: Number(summary.positiveValidationFolds || 0),
        total: Number(summary.validationFolds || 0),
        validation: this.formatPercent(summary.oosReturn),
        blind: this.formatPercent(summary.blindReturn),
        evaluated,
        minimum,
        space: space.toLocaleString(),
        coverage: coverage > 0 && coverage < 0.01 ? '<0.01%' : `${coverage.toFixed(2)}%`
      }
    },
    datePresets () {
      const end = (this.form.endDate || moment().subtract(1, 'day')).clone().startOf('day')
      const rows = [
        { key: '1m', startDate: end.clone().subtract(1, 'month') },
        { key: '3m', startDate: end.clone().subtract(3, 'months') },
        { key: '6m', startDate: end.clone().subtract(6, 'months') }
      ]
      const presets = rows.map(row => {
        const rangeDays = end.diff(row.startDate, 'days')
        return {
          ...row,
          label: this.$t(`strategyEvolution.quickRange.${row.key}`),
          disabled: this.backtestRangeLimitDays !== null && rangeDays > this.backtestRangeLimitDays,
          active: this.selectedRangeDays === rangeDays
        }
      })
      if (this.backtestRangeLimitDays !== null) {
        presets.push({
          key: 'max',
          startDate: end.clone().subtract(this.backtestRangeLimitDays, 'days'),
          label: this.$t('strategyEvolution.quickRange.max', { days: this.backtestRangeLimitDays }),
          disabled: false,
          active: this.selectedRangeDays === this.backtestRangeLimitDays
        })
      }
      return presets
    },
    canRun () { return Boolean(!this.loadingSource && this.form.sourceId && this.selectedParameterCount && this.parameterRangesValid && this.form.startDate && this.form.endDate && !this.backtestRangeExceeded) }
  },
  watch: {
    form: { handler: 'scheduleEstimate', deep: true },
    parameterSpace: { handler: 'scheduleEstimate', deep: true },
    parameterEnabled: { handler: 'scheduleEstimate', deep: true },
    isDarkTheme () { this.refreshChartsForTheme() },
    primaryColor () { this.refreshChartsForTheme() }
  },
  mounted () { this.initializeWorkspace(); window.addEventListener('resize', this.resizeCharts) },
  beforeDestroy () { window.removeEventListener('resize', this.resizeCharts); this.disposeCharts(); this.stopPolling(); this.estimateRequestId += 1; if (this.estimateTimer) window.clearTimeout(this.estimateTimer) },
  methods: {
    async initializeWorkspace () {
      const allHistory = await this.fetchHistory()
      const active = allHistory.find(job => ['queued', 'running'].includes(job.status))
      if (active && active.request) this.form.sourceId = active.request.sourceId
      await this.loadSources()
      this.scheduleEstimate()
    },
    async loadSources () {
      this.loadingSources = true
      try {
        const response = await getScriptSourceList()
        this.sources = (response.data && response.data.items) || []
        if (!this.form.sourceId && this.sources.length) this.form.sourceId = this.sources[0].id
        if (this.form.sourceId) await this.selectSource(this.form.sourceId)
      } finally { this.loadingSources = false }
    },
    async selectSource (sourceId) {
      this.stopPolling()
      this.disposeCharts()
      this.running = false
      this.jobId = ''
      this.progress = {}
      this.result = null
      await this.loadSource(sourceId)
      await this.loadHistory(sourceId)
      const active = this.history.find(job => ['queued', 'running'].includes(job.status))
      if (!active) return
      this.applyHistoryRequest(active.request)
      this.jobId = active.jobId
      this.progress = active.progress || {}
      this.running = true
      await this.pollStudy()
    },
    async loadSource (sourceId) {
      this.loadingSource = true
      try {
        const [response, compiled, parameterSpaceResponse] = await Promise.all([
          getScriptSourceDetail(sourceId),
          compileScriptSource({ sourceId }),
          getStrategyEvolutionParameterSpace(sourceId)
        ])
        this.source = response.data || null
        this.manifest = compiled.data && compiled.data.manifest
        this.backtestRangePolicy = compiled.data && compiled.data.backtestRangePolicy
        this.parameterContract = parameterSpaceResponse.data || null
        this.parameterDefinitions = (this.parameterContract && this.parameterContract.parameters) || []
        const enabled = {}; const space = {}
        this.parameterDefinitions.forEach(item => {
          enabled[item.name] = this.searchableParameter(item) && item.defaultSelected !== false
          space[item.name] = {
            min: item.recommendedMin !== undefined ? item.recommendedMin : item.min,
            max: item.recommendedMax !== undefined ? item.recommendedMax : item.max,
            step: item.step
          }
        })
        this.parameterEnabled = enabled; this.parameterSpace = space; this.result = null
        this.applyBacktestRangePolicy()
      } catch (error) {
        this.manifest = null
        this.backtestRangePolicy = null
        this.parameterContract = null
        this.parameterDefinitions = []
        this.parameterEnabled = {}
        this.parameterSpace = {}
        this.$message.error((error && error.backendMessage) || this.$t('strategyEvolution.sourceLoadFailed'))
      } finally {
        this.loadingSource = false
      }
    },
    applyBacktestRangePolicy () {
      if (this.backtestRangeLimitDays === null || !this.form.endDate) return
      const endDate = this.form.endDate.clone().startOf('day')
      this.form.startDate = endDate.clone().subtract(this.backtestRangeLimitDays, 'days')
    },
    applyDatePreset (preset) {
      if (!preset || preset.disabled) return
      this.form.startDate = preset.startDate.clone()
    },
    numericParameter (item) { return ['int', 'integer', 'float', 'number', 'percent'].includes(item.type) },
    booleanParameter (item) { return ['bool', 'boolean'].includes(item.type) },
    selectSearchMethod (method) {
      this.form.method = method
      if (method === 'tpe' && Number(this.form.trials) < this.trialMinimum) this.form.trials = 64
      if (Number(this.form.trials) > this.trialMaximum) this.form.trials = this.trialMaximum
    },
    applyBudgetPreset (preset) {
      this.form.trials = preset.trials
      this.form.folds = preset.folds
      this.form.autoPrune = false
    },
    parameterChoices (item) {
      return (item.choices || item.options || item.values || []).map(value => (value && typeof value === 'object' ? value.value : value))
    },
    searchableParameter (item) {
      if (item.optimizable === false) return false
      const choices = this.parameterChoices(item)
      const boundedNumeric = this.numericParameter(item) && item.min !== undefined && item.min !== null && item.max !== undefined && item.max !== null
      return boundedNumeric || ['bool', 'boolean'].includes(item.type) || Boolean(choices.length)
    },
    parameterLabel (item) { return strategyParameterLabel(item, key => this.$t(key)) },
    toggleParameter (name, enabled) { this.parameterEnabled = { ...this.parameterEnabled, [name]: enabled } },
    parameterStepMinimum (item) {
      if (['int', 'integer'].includes(item.type)) return 1
      return Math.max(Math.abs(Number(item.step || 0.0001)) / 10, 0.00000001)
    },
    parameterStepIncrement (item) { return this.parameterStepMinimum(item) },
    parameterStepMaximum (item) {
      const range = this.parameterSpace[item.name] || {}
      return Math.max(this.parameterStepMinimum(item), Number(range.max) - Number(range.min))
    },
    parameterDomainSize (item) {
      if (this.booleanParameter(item)) return 2
      const choices = this.parameterChoices(item)
      if (choices.length) return choices.length
      if (!this.numericParameter(item)) return 1
      const range = this.parameterSpace[item.name] || {}
      const minimum = Number(range.min); const maximum = Number(range.max); const step = Number(range.step)
      if (![minimum, maximum, step].every(Number.isFinite) || step <= 0 || maximum <= minimum) return 1
      const span = maximum - minimum
      const regularSteps = Math.floor((span / step) + 1e-12)
      const regularMaximum = minimum + regularSteps * step
      const tolerance = Math.max(1, Math.abs(minimum), Math.abs(maximum)) * 1e-10
      return regularSteps + 1 + (regularMaximum < maximum - tolerance ? 1 : 0)
    },
    effectivePresetTrials (preset) {
      const requested = Math.max(1, Number(preset && preset.trials) || 1)
      return this.localSearchSpaceSize > 0 ? Math.min(requested, this.localSearchSpaceSize) : requested
    },
    updateParameterRange (name, boundary, value) {
      this.parameterSpace = { ...this.parameterSpace, [name]: { ...(this.parameterSpace[name] || {}), [boundary]: value } }
    },
    resetParameterRange (item) {
      this.parameterSpace = { ...this.parameterSpace, [item.name]: { min: item.recommendedMin !== undefined ? item.recommendedMin : item.min, max: item.recommendedMax !== undefined ? item.recommendedMax : item.max, step: item.step } }
    },
    inferAvailableChecks () {
      const validation = (this.result && this.result.validation) || {}
      return ['pbo', 'deflatedSharpe', 'monteCarlo'].filter(key => validation[key] && validation[key].available).length + ((validation.costStress || []).some(row => Number(row.activity || 0) > 0) ? 1 : 0)
    },
    formatParameterValue (value) {
      const number = Number(value)
      if (!Number.isFinite(number)) return '—'
      return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(8)))
    },
    parameterPayload () { return this.parameterDefinitions.filter(item => this.parameterEnabled[item.name]).map(item => ({ ...item, ...(this.parameterSpace[item.name] || {}) })) },
    estimatePayload () {
      return { parameterSpace: this.parameterPayload(), config: { method: this.form.method, trials: this.form.trials, folds: this.form.folds, trainRatio: this.form.trainRatio, blindRatio: this.form.blindRatio, autoPrune: this.form.autoPrune, monteCarloPaths: 1000 } }
    },
    scheduleEstimate () {
      const requestId = ++this.estimateRequestId
      if (this.estimateTimer) window.clearTimeout(this.estimateTimer)
      this.estimate = null
      this.estimateLoading = Boolean(this.selectedParameterCount && this.parameterRangesValid)
      this.estimateTimer = window.setTimeout(() => this.refreshEstimate(requestId), 250)
    },
    async refreshEstimate (requestId = this.estimateRequestId) {
      this.estimateTimer = null
      if (requestId !== this.estimateRequestId) return
      if (!this.selectedParameterCount || !this.parameterRangesValid) { this.estimate = null; this.estimateLoading = false; return }
      try {
        const response = await estimateStrategyEvolution(this.estimatePayload())
        if (requestId === this.estimateRequestId) this.estimate = response.data || null
      } catch (error) {
        if (requestId === this.estimateRequestId) this.estimate = null
      } finally {
        if (requestId === this.estimateRequestId) this.estimateLoading = false
      }
    },
    async fetchHistory (sourceId) {
      const params = { limit: 20 }
      if (sourceId !== undefined && sourceId !== null && sourceId !== '') params.sourceId = sourceId
      const response = await getStrategyEvolutionJobs(params)
      return (response.data && response.data.items) || []
    },
    async loadHistory (sourceId = this.form.sourceId) {
      const requestId = ++this.historyRequestId
      this.historyLoading = true
      try {
        const items = await this.fetchHistory(sourceId)
        if (requestId === this.historyRequestId && Number(sourceId) === Number(this.form.sourceId)) this.history = items
      } catch (error) {
        if (requestId === this.historyRequestId) this.history = []
      } finally {
        if (requestId === this.historyRequestId) this.historyLoading = false
      }
    },
    applyHistoryRequest (request = {}) {
      const config = request.config || {}
      if (request.sourceId) this.form.sourceId = request.sourceId
      if (request.startDate) this.form.startDate = moment(request.startDate)
      if (request.endDate) this.form.endDate = moment(request.endDate)
      ;['method', 'trials', 'folds', 'trainRatio', 'blindRatio', 'autoPrune'].forEach(key => {
        if (config[key] !== undefined) this.form[key] = config[key]
      })
      if (this.form.method === 'tpe' && Number(this.form.trials) < 32) this.form.trials = 32
      if (request.commission !== undefined) this.form.commission = request.commission
      if (request.slippage !== undefined) this.form.slippage = request.slippage
      const requested = new Map((request.parameterSpace || []).map(item => [item.name, item]))
      if (requested.size) {
        const enabled = {}; const space = { ...this.parameterSpace }
        this.parameterDefinitions.forEach(item => {
          const saved = requested.get(item.name)
          enabled[item.name] = Boolean(saved)
          if (saved) space[item.name] = { min: saved.min, max: saved.max, step: saved.step !== undefined ? saved.step : item.step }
        })
        this.parameterEnabled = enabled
        this.parameterSpace = space
      }
    },
    async openHistory (job) {
      this.stopPolling()
      this.disposeCharts()
      let selected = job
      try {
        const response = await getStrategyEvolutionJob(job.jobId)
        selected = response.data || job
      } catch (error) {
        this.$message.error((error && error.backendMessage) || this.$t('strategyEvolution.jobNotFound'))
        return
      }
      this.jobId = selected.jobId
      if (selected.request && selected.request.sourceId && selected.request.sourceId !== this.form.sourceId) {
        this.form.sourceId = selected.request.sourceId
        await this.loadSource(selected.request.sourceId)
      }
      this.applyHistoryRequest(selected.request)
      this.progress = selected.progress || {}
      this.running = ['queued', 'running'].includes(selected.status)
      this.result = selected.status === 'succeeded' ? selected.result : null
      if (this.running) await this.pollStudy()
      if (this.result) { await this.$nextTick(); this.renderCharts() }
    },
    historySourceName (job) {
      if (job.result && job.result.source && job.result.source.name) return job.result.source.name
      const sourceId = job.request && job.request.sourceId
      const source = this.sources.find(item => Number(item.id) === Number(sourceId))
      return (source && source.name) || this.$t('strategyEvolution.historyStudy')
    },
    historyMethod (job) { return this.$t(`strategyEvolution.method.${((job.request || {}).config || {}).method || 'tpe'}`) },
    historyDateRange (job) { const request = job.request || {}; return request.startDate && request.endDate ? `${request.startDate} – ${request.endDate}` : '—' },
    formatDateTime (value) { return value ? moment(value).format('YYYY-MM-DD HH:mm') : '—' },
    formatFoldRange (start, end) { return start && end ? `${moment(start).format('YYYY-MM-DD')} – ${moment(end).format('YYYY-MM-DD')}` : '—' },
    applyBestParams () {
      this.$emit('apply', {
        sourceId: this.form.sourceId,
        params: this.result.bestParams,
        parameterDefinitions: this.parameterDefinitions,
        recommended: this.recommendBest
      })
    },
    async runStudy () {
      if (Number(this.form.trials) < this.trialMinimum) {
        this.form.trials = this.trialMinimum
        this.$message.info(this.$t('strategyEvolution.budgetRaised', { trials: this.trialMinimum }))
      }
      this.running = true; this.result = null; this.progress = {}; this.disposeCharts()
      try {
        const response = await runStrategyEvolution({ sourceId: this.form.sourceId, startDate: this.form.startDate.format('YYYY-MM-DD'), endDate: this.form.endDate.format('YYYY-MM-DD'), initialCapital: 10000, commission: this.form.commission, slippage: this.form.slippage, parameterSpace: this.parameterPayload(), config: { method: this.form.method, trials: this.form.trials, folds: this.form.folds, trainRatio: this.form.trainRatio, blindRatio: this.form.blindRatio, autoPrune: this.form.autoPrune, monteCarloPaths: 1000 } })
        this.jobId = String((response.data && response.data.jobId) || '')
        if (!this.jobId) throw new Error('strategyEvolution.jobNotCreated')
        await this.loadHistory()
        await this.pollStudy()
      } catch (error) {
        this.$message.error((error && error.backendMessage) || this.$t('strategyEvolution.runFailed'))
        this.running = false
      }
    },
    async pollStudy () {
      if (!this.running || !this.jobId) return
      try {
        const response = await getStrategyEvolutionJob(this.jobId)
        const job = response.data || {}
        this.progress = job.progress || {}
        if (job.status === 'succeeded') {
          this.result = job.result
          this.running = false
          this.stopPolling()
          await this.loadHistory()
          await this.$nextTick()
          this.renderCharts()
          return
        }
        if (job.status === 'failed' || job.status === 'cancelled') {
          this.running = false
          this.stopPolling()
          await this.loadHistory()
          if (job.status === 'failed') this.$message.error(this.jobFailureMessage(job))
          return
        }
        this.pollTimer = window.setTimeout(this.pollStudy, 1500)
      } catch (error) {
        this.pollTimer = window.setTimeout(this.pollStudy, 2500)
      }
    },
    async cancelStudy () {
      if (!this.jobId) return
      await cancelStrategyEvolutionJob(this.jobId)
      this.running = false
      this.stopPolling()
      await this.loadHistory()
      this.$message.info(this.$t('strategyEvolution.cancelled'))
    },
    stopPolling () { if (this.pollTimer) window.clearTimeout(this.pollTimer); this.pollTimer = null },
    jobFailureMessage (job) {
      const failure = job && job.progress && job.progress.failure
      if (failure && failure.messageKey && this.$te(failure.messageKey)) {
        const counts = failure.reasonCounts || {}
        return this.$t(failure.messageKey, {
          count: counts[failure.dominantReason] || 0,
          total: failure.totalTrials || 0,
          training: failure.activeTrainingTrials || 0,
          validation: failure.activeValidationTrials || 0,
          runs: failure.actualBacktestRuns || 0
        })
      }
      const raw = String((job && job.error) || (job && job.progress && job.progress.error) || '').split(/\r?\n/, 1)[0].trim()
      if (!raw) return this.$t('strategyEvolution.runFailed')
      return this.$te(raw) ? this.$t(raw) : raw
    },
    renderCharts () {
      const palette = this.chartPalette()
      const { text, grid, accent, accentArea, cyan, red, redArea, tooltipBackground, tooltipText } = palette
      const tooltip = { trigger: 'axis', backgroundColor: tooltipBackground, borderColor: grid, textStyle: { color: tooltipText }, valueFormatter: value => this.chartNumber(value) }
      const curve = this.result.equityCurve || []
      this.makeChart(this.$refs.equityChart, { tooltip, grid: { left: 62, right: 18, top: 30, bottom: 42 }, xAxis: { type: 'category', data: curve.map(row => row.time), axisLabel: { color: text, hideOverlap: true }, axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', scale: true, axisLabel: { color: text, formatter: value => this.chartNumber(value) }, splitLine: { lineStyle: { color: grid } } }, dataZoom: [{ type: 'inside' }], series: [{ type: 'line', data: curve.map(row => row.value), symbol: 'none', lineStyle: { color: accent, width: 2 }, areaStyle: { color: accentArea } }] })
      this.makeChart(this.$refs.drawdownChart, { tooltip, grid: { left: 50, right: 15, top: 22, bottom: 35 }, xAxis: { type: 'category', data: curve.map(row => row.time), axisLabel: { color: text, hideOverlap: true }, axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', axisLabel: { color: text, formatter: '{value}%' }, splitLine: { lineStyle: { color: grid } } }, series: [{ type: 'line', data: curve.map(row => row.drawdown || 0), symbol: 'none', lineStyle: { color: red }, areaStyle: { color: redArea } }] })
      const convergence = this.result.convergence || []
      this.makeChart(this.$refs.convergenceChart, { tooltip, grid: { left: 45, right: 15, top: 20, bottom: 35 }, xAxis: { type: 'category', data: convergence.map(row => row.trial), axisLabel: { color: text } }, yAxis: { type: 'value', axisLabel: { color: text }, splitLine: { lineStyle: { color: grid } } }, series: [{ type: 'scatter', data: convergence.map(row => row.score), itemStyle: { color: cyan } }, { type: 'line', data: convergence.map(row => row.best), symbol: 'none', lineStyle: { color: accent } }] })
      const heat = this.result.heatmap || { points: [] }
      this.makeChart(this.$refs.heatmapChart, { tooltip, grid: { left: 55, right: 20, top: 20, bottom: 45 }, xAxis: { type: 'value', name: heat.xParameter, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', name: heat.yParameter, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: grid } } }, visualMap: { min: 0, max: 100, show: false, inRange: { color: [red, '#c9951a', accent] } }, series: [{ type: 'scatter', symbolSize: 16, data: heat.points }] })
      const histogram = (((this.result.validation || {}).monteCarlo || {}).terminalReturns) || []
      this.makeChart(this.$refs.monteCarloChart, { title: histogram.length ? undefined : this.emptyChartTitle(text), tooltip, grid: { left: 54, right: 18, top: 30, bottom: 42 }, xAxis: { type: 'category', data: histogram.map(row => row.value), axisLabel: { color: text, interval: 4, formatter: value => this.chartNumber(value) }, axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', axisLabel: { color: text }, splitLine: { lineStyle: { color: grid } } }, series: [{ type: 'bar', data: histogram.map(row => row.count), itemStyle: { color: cyan } }] })
      const costs = ((this.result.validation || {}).costStress) || []
      this.makeChart(this.$refs.costChart, { title: costs.some(row => Number(row.activity || 0) > 0) ? undefined : this.emptyChartTitle(text), tooltip, grid: { left: 54, right: 18, top: 30, bottom: 42 }, xAxis: { type: 'category', data: costs.map(row => `${row.multiplier}×`), axisLabel: { color: text }, axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', axisLabel: { color: text, formatter: value => `${this.chartNumber(value)}%` }, splitLine: { lineStyle: { color: grid } } }, series: [{ type: 'bar', data: costs.map(row => row.return), itemStyle: { color: params => params.value >= 0 ? accent : red } }] })
    },
    chartPalette () {
      const styles = this.$el && window.getComputedStyle(this.$el)
      const read = (name, fallback) => (styles && styles.getPropertyValue(name).trim()) || fallback
      return {
        text: read('--evo-chart-text', this.isDarkTheme ? '#8b949e' : '#667085'),
        grid: read('--evo-chart-grid', this.isDarkTheme ? '#2d2d2d' : '#e5e7eb'),
        accent: read('--evo-accent', '#52c41a'),
        accentArea: read('--evo-chart-accent-area', this.isDarkTheme ? 'rgba(82,196,26,.1)' : 'rgba(82,196,26,.08)'),
        cyan: read('--evo-chart-secondary', '#20c8c8'),
        red: read('--evo-danger', '#ff5a5f'),
        redArea: read('--evo-chart-danger-area', this.isDarkTheme ? 'rgba(255,90,95,.14)' : 'rgba(255,90,95,.1)'),
        tooltipBackground: read('--evo-tooltip-bg', this.isDarkTheme ? '#181818' : '#ffffff'),
        tooltipText: read('--evo-tooltip-text', this.isDarkTheme ? '#f4f7f5' : '#1f2937')
      }
    },
    refreshChartsForTheme () {
      this.$nextTick(() => {
        if (!this.result) return
        this.disposeCharts()
        this.renderCharts()
      })
    },
    makeChart (element, option) { if (!element) return; const chart = echarts.init(element); chart.setOption(option); this.charts.push(chart) },
    disposeCharts () { this.charts.forEach(chart => chart.dispose()); this.charts = [] },
    resizeCharts () { this.charts.forEach(chart => chart.resize()) },
    formatPercent (value) { return `${Number(value || 0).toFixed(2)}%` },
    formatNumber (value) { return Number(value || 0).toFixed(2) },
    formatDuration (value) {
      const seconds = Math.max(0, Math.round(Number(value) || 0))
      const minutes = Math.floor(seconds / 60)
      return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`
    },
    chartNumber (value) {
      const number = Number(value)
      if (!Number.isFinite(number)) return '—'
      const magnitude = Math.abs(number)
      const decimals = magnitude >= 1000 ? 0 : magnitude >= 10 ? 2 : 4
      return decimals ? number.toFixed(decimals).replace(/\.?0+$/, '') : number.toFixed(0)
    },
    emptyChartTitle (color) { return { text: this.$t('strategyEvolution.validationInsufficient'), left: 'center', top: 'middle', textStyle: { color, fontSize: 11, fontWeight: 'normal' } } },
    formatParams (params) { return Object.entries(params || {}).map(([key, value]) => `${key}=${value}`).join(' · ') }
  }
}
</script>

<style lang="less" scoped>
.evolution-shell {
  --evo-accent: var(--primary-color, #52c41a);
  --evo-page: #f1f3f5;
  --evo-panel: #ffffff;
  --evo-surface: #fafbfc;
  --evo-surface-strong: #f7f9fb;
  --evo-input: #ffffff;
  --evo-border: #e2e6eb;
  --evo-border-soft: #edf0f4;
  --evo-heading: #17233d;
  --evo-text: #445269;
  --evo-muted: #718096;
  --evo-faint: #7c8ca1;
  --evo-disabled: #a9b1b7;
  --evo-danger: #e5484d;
  --evo-warning: #c58b14;
  --evo-shadow: rgba(35, 49, 60, .09);
  --evo-chart-text: #667085;
  --evo-chart-grid: #e5e9ed;
  --evo-chart-secondary: #20aeb5;
  --evo-chart-accent-area: color-mix(in srgb, var(--evo-accent) 12%, transparent);
  --evo-chart-danger-area: rgba(229, 72, 77, .10);
  --evo-tooltip-bg: #ffffff;
  --evo-tooltip-text: #1f2937;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 332px minmax(620px, 1fr) 260px;
  gap: 10px;
  height: calc(100vh - 150px);
  min-height: 0;
  padding: 0;
  overflow: hidden;
  color: var(--evo-text);
  background: transparent;
  color-scheme: light;
  font-size: 12px;
}
.evolution-shell.theme-dark {
  --evo-page: #080808;
  --evo-panel: #111111;
  --evo-surface: #151515;
  --evo-surface-strong: #0d0d0d;
  --evo-input: #181818;
  --evo-border: #2d2d2d;
  --evo-border-soft: #242424;
  --evo-heading: #f4f7f5;
  --evo-text: #dce2de;
  --evo-muted: #8d9792;
  --evo-faint: #737d82;
  --evo-disabled: #596368;
  --evo-danger: #ff6d72;
  --evo-warning: #d7aa2b;
  --evo-shadow: rgba(0, 0, 0, .24);
  --evo-chart-text: #8b949e;
  --evo-chart-grid: #2d2d2d;
  --evo-chart-secondary: #20c8c8;
  --evo-chart-accent-area: color-mix(in srgb, var(--evo-accent) 13%, transparent);
  --evo-chart-danger-area: rgba(255, 90, 95, .14);
  --evo-tooltip-bg: #181818;
  --evo-tooltip-text: #f4f7f5;
  color-scheme: dark;
}
.evolution-rail, .evolution-main { min-width: 0; min-height: 0; border: 1px solid var(--evo-border); border-radius: 10px; background: var(--evo-panel); box-shadow: 0 6px 20px rgba(15, 35, 60, .045); }
.evolution-rail { display: flex; overflow: hidden; flex-direction: column; }
.evolution-rail__title { display: grid; grid-template-columns: 18px minmax(0, 1fr) 24px; gap: 8px; align-items: start; padding: 14px; border-bottom: 1px solid var(--evo-border); color: var(--evo-accent); }
.evolution-rail__title > i { margin-top: 2px; font-size: 16px; }
.evolution-rail__title div { display: flex; min-width: 0; flex-direction: column; }
.evolution-rail__title strong { color: var(--evo-heading); font-size: 14px; line-height: 1.4; }
.evolution-rail__title span { margin-top: 3px; color: var(--evo-muted); font-size: 11px; line-height: 1.5; }
.evolution-scroll { min-height: 0; padding: 10px 10px 4px; overflow: auto; scrollbar-gutter: stable; flex: 1; }
.evolution-section { margin-bottom: 10px; padding: 12px; border: 1px solid var(--evo-border); border-radius: 10px; background: var(--evo-surface); }
.evolution-section__heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 24px; margin-bottom: 10px; }
.evolution-section__heading > div { display: flex; min-width: 0; align-items: center; gap: 9px; }
.evolution-section__heading h3 { overflow: hidden; margin: 0; color: var(--evo-heading); font-size: 14px; font-weight: 700; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.evolution-section__heading > span { flex: 0 0 auto; color: var(--evo-faint); font-size: 11px; font-variant-numeric: tabular-nums; }
.step-badge { display: inline-grid; place-items: center; width: 22px; height: 22px; flex: 0 0 22px; border-radius: 7px; color: var(--evo-accent); background: color-mix(in srgb, var(--evo-accent) 10%, var(--evo-panel)); font-size: 11px; font-weight: 800; }
.field-label { display: block; margin-bottom: 7px; color: var(--evo-text); font-size: 12px; font-weight: 600; }
.evolution-section > label, .section-line label { display: block; margin-bottom: 8px; color: var(--evo-text); font-size: 12px; font-weight: 600; }
.section-line { display: flex; justify-content: space-between; }
.section-line span, .evolution-muted { color: var(--evo-faint); font-size: 11px; }
.full-width { width: 100%; }
.parameter-space-hint { display: grid; grid-template-columns: 16px minmax(0, 1fr); gap: 7px; align-items: start; margin-bottom: 10px; padding: 9px 0 10px; border-bottom: 1px solid var(--evo-border); border-radius: 0; color: var(--evo-muted); background: transparent; font-size: 11px; line-height: 1.5; }
.parameter-space-hint > i { margin-top: 2px; color: var(--evo-accent); }
.parameter-scope-alert { margin-bottom: 8px; }
.parameter-scope-alert,
.sample-alert { border-color: var(--evo-border); border-left-width: 3px; border-radius: 8px; background: var(--evo-surface-strong); }
.parameter-scope-alert /deep/ .ant-alert-message,
.sample-alert /deep/ .ant-alert-message { color: var(--evo-text); }
.parameter-row { margin-top: 8px; padding: 10px; border: 1px solid var(--evo-border-soft); border-radius: 8px; background: var(--evo-panel); }
.parameter-row__title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.parameter-row__title /deep/ .ant-checkbox-wrapper { color: var(--evo-text); }
.parameter-row__title /deep/ .ant-checkbox-inner { border-color: var(--evo-border); background: var(--evo-input); }
.parameter-row__title /deep/ .ant-checkbox-checked .ant-checkbox-inner { border-color: var(--evo-accent); background: var(--evo-accent); }
.parameter-row--disabled { opacity: .5; }
.parameter-row--disabled .parameter-row__title /deep/ .ant-checkbox-wrapper { color: var(--evo-disabled); }
.parameter-row code { max-width: 42%; overflow: hidden; color: var(--evo-faint); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.parameter-domain { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-top: 9px; color: var(--evo-text); font-variant-numeric: tabular-nums; }
.parameter-domain > label { min-width: 0; }
.parameter-domain > label > span { display: block; margin-bottom: 4px; color: var(--evo-muted); font-size: 10px; line-height: 1.3; }
.parameter-domain > span { min-width: 48px; padding: 6px 8px; border: 1px solid var(--evo-border); border-radius: 7px; background: var(--evo-input); text-align: center; }
.parameter-domain /deep/ .ant-input-number { width: 100%; height: 32px; border-color: var(--evo-border); border-radius: 7px; background: var(--evo-input); }
.parameter-domain /deep/ .ant-input-number-input { color: var(--evo-heading); background: transparent; }
.parameter-domain /deep/ .ant-input-number-handler-wrap { border-color: var(--evo-border); background: var(--evo-surface-strong); }
.parameter-domain /deep/ .ant-input-number-handler { border-color: var(--evo-border); }
.parameter-domain /deep/ .ant-btn-link { height: 22px; margin-left: auto; padding: 0; color: var(--evo-accent); font-size: 10px; }
.parameter-domain i, .parameter-domain small { color: var(--evo-faint); font-style: normal; }
.parameter-domain small { min-width: 0; font-size: 10px; }
.parameter-domain__footer { grid-column-start: 1; grid-column-end: 4; display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 8px; min-height: 22px; }
.parameter-domain__footer small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.two-col .ant-input-number { width: 100%; }
.two-col .ant-form-item { margin: 10px 0 0; }
.two-col /deep/ .ant-form-item-label > label { color: var(--evo-muted); }
.switch-setting { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; color: var(--evo-muted); }
.evolution-section /deep/ .ant-select-selection, .evolution-section /deep/ .ant-calendar-picker-input, .evolution-section /deep/ .ant-input-number { border-color: var(--evo-border); color: var(--evo-heading); background: var(--evo-input); }
.evolution-section /deep/ .ant-select-selection, .evolution-section /deep/ .ant-calendar-picker-input { height: 34px; border-radius: 7px; }
.evolution-section /deep/ .ant-select-selection__rendered { line-height: 32px; }
.evolution-section /deep/ .ant-select-selection__rendered, .evolution-section /deep/ .ant-calendar-picker-icon, .evolution-section /deep/ .ant-select-arrow { color: var(--evo-muted); }
.method-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.method-card { min-width: 0; min-height: 58px; padding: 9px 5px; border: 1px solid var(--evo-border); border-radius: 8px; color: var(--evo-muted); background: var(--evo-panel); cursor: pointer; }
.method-card > i { display: block; margin-bottom: 5px; font-size: 15px; }
.method-card span, .method-card strong, .method-card small { display: block; }
.method-card strong { overflow: hidden; color: var(--evo-text); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.method-card small { margin-top: 2px; overflow: hidden; color: var(--evo-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.method-card--active { border-color: var(--evo-accent); color: var(--evo-accent); background: color-mix(in srgb, var(--evo-accent) 9%, var(--evo-panel)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--evo-accent) 14%, transparent); }
.method-card--active strong { color: var(--evo-heading); }
.method-card--active small { color: color-mix(in srgb, var(--evo-accent) 74%, var(--evo-muted)); }
.budget-presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 8px; }
.budget-presets button { min-width: 0; min-height: 48px; padding: 7px 4px; border: 1px solid var(--evo-border); border-radius: 8px; color: var(--evo-muted); background: var(--evo-panel); cursor: pointer; }
.budget-presets strong, .budget-presets small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.budget-presets strong { color: var(--evo-text); font-size: 11px; }
.budget-presets small { margin-top: 3px; color: var(--evo-muted); font-size: 10px; line-height: 1.35; white-space: normal; }
.budget-presets button.active { border-color: var(--evo-accent); background: color-mix(in srgb, var(--evo-accent) 9%, var(--evo-panel)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--evo-accent) 14%, transparent); }
.budget-presets button.active strong { color: var(--evo-accent); }
.effective-budget { margin: 5px 0 0; color: var(--evo-muted); font-size: 10px; line-height: 1.45; }
.sample-alert { margin-top: 8px; }
.sample-alert /deep/ .ant-alert-message { font-size: 11px; line-height: 1.45; }
.date-presets { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-bottom: 8px; }
.date-presets /deep/ .ant-btn { min-width: 0; padding: 0 4px; border-color: var(--evo-border); border-radius: 7px; color: var(--evo-muted); background: var(--evo-panel); font-size: 11px; }
.date-presets /deep/ .ant-btn:hover:not([disabled]) { border-color: var(--evo-accent); color: var(--evo-accent); }
.date-presets /deep/ .ant-btn-primary { border-color: var(--evo-accent); color: #fff; background: var(--evo-accent); box-shadow: 0 3px 10px color-mix(in srgb, var(--evo-accent) 24%, transparent); }
.date-range-fields { display: grid; grid-template-columns: minmax(0, 1fr) 18px minmax(0, 1fr); gap: 5px; align-items: end; }
.date-range-fields > label { min-width: 0; }
.date-range-fields > label > span { display: block; margin-bottom: 4px; color: var(--evo-muted); font-size: 10px; }
.date-range-fields > i { display: grid; place-items: center; height: 34px; color: var(--evo-faint); font-size: 9px; }
.evolution-runbar { z-index: 2; flex: 0 0 auto; padding: 11px 14px 13px; border-top: 1px solid var(--evo-border); background: var(--evo-panel); box-shadow: 0 -10px 22px var(--evo-shadow); }
.resource-estimate { display: flex; justify-content: space-between; margin-bottom: 4px; color: var(--evo-faint); font-size: 11px; }
.resource-estimate strong { color: var(--evo-text); }
.resource-estimate--runs strong { color: var(--evo-accent); }
.estimate-hint { margin: 3px 0 9px; color: var(--evo-muted); font-size: 10px; line-height: 1.4; }
.run-actions { display: grid; grid-template-columns: auto 1fr; gap: 8px; }
.evolution-main { overflow: auto; padding: 16px; background: var(--evo-panel); }
.evolution-empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--evo-muted); text-align: center; }
.evolution-empty--setup { height: auto; min-height: 0; align-items: stretch; justify-content: flex-start; padding: 18px; border: 1px solid var(--evo-border); border-radius: 10px; background: var(--evo-surface); text-align: left; }
.empty-icon { display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid var(--evo-border); border-radius: 8px; background: var(--evo-panel); color: var(--evo-accent); font-size: 18px; box-shadow: none; }
.evolution-empty h2 { margin: 14px 0 4px; color: var(--evo-heading); font-size: 15px; line-height: 1.45; }
.evolution-empty p { max-width: 680px; margin: 0; font-size: 12px; line-height: 1.6; }
.empty-flow { display: grid; grid-template-columns: repeat(5, auto); align-items: center; justify-content: start; gap: 8px; margin-top: 14px; }
.empty-flow span { padding: 7px 10px; border: 1px solid var(--evo-border); border-radius: 7px; color: var(--evo-text); background: var(--evo-panel); font-size: 11px; }
.empty-flow > i { color: var(--evo-faint); }
.running-spinner { color: var(--evo-accent); font-size: 42px; }
.evolution-progress { width: 80%; max-width: 520px; margin-top: 16px; }
.result-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; }
.result-header h2 { margin: 3px 0 0; color: var(--evo-heading); }
.eyebrow { color: var(--evo-accent); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
.metric-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 10px; }
.metric-grid article { position: relative; min-width: 0; padding: 12px; border: 1px solid var(--evo-border); border-radius: 9px; background: var(--evo-surface); }
.metric-grid span { display: block; color: var(--evo-faint); font-size: 10px; }
.metric-grid strong { display: block; margin-top: 5px; color: var(--evo-heading); font-size: 21px; }
.metric-grid em { position: absolute; top: 12px; right: 12px; color: var(--evo-accent); font-style: normal; font-weight: 700; }
.negative { color: var(--evo-danger) !important; }
.research-verdict { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; gap: 12px; align-items: center; min-height: 76px; margin-bottom: 10px; padding: 12px 14px; border: 1px solid color-mix(in srgb, var(--evo-accent) 34%, var(--evo-border)); border-left: 3px solid var(--evo-accent); border-radius: 9px; background: linear-gradient(100deg, color-mix(in srgb, var(--evo-accent) 8%, var(--evo-panel)), var(--evo-surface-strong) 62%); box-shadow: 0 4px 16px var(--evo-shadow); }
.research-verdict--review { border-color: color-mix(in srgb, var(--evo-warning) 30%, var(--evo-border)); border-left-color: var(--evo-warning); background: linear-gradient(100deg, color-mix(in srgb, var(--evo-warning) 7%, var(--evo-panel)), var(--evo-surface-strong) 62%); }
.research-verdict__icon { display: grid; place-items: center; width: 32px; height: 32px; border: 1px solid color-mix(in srgb, var(--evo-accent) 48%, var(--evo-border)); border-radius: 50%; color: var(--evo-accent); background: color-mix(in srgb, var(--evo-accent) 10%, var(--evo-panel)); }
.research-verdict--review .research-verdict__icon { border-color: color-mix(in srgb, var(--evo-warning) 48%, var(--evo-border)); color: var(--evo-warning); background: color-mix(in srgb, var(--evo-warning) 9%, var(--evo-panel)); }
.research-verdict__copy { min-width: 0; }
.research-verdict__copy > span { display: block; margin-bottom: 2px; color: var(--evo-faint); font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.research-verdict__copy strong { color: var(--evo-heading); font-size: 13px; }
.research-verdict__copy p { margin: 3px 0 0; color: var(--evo-muted); font-size: 10px; line-height: 1.45; }
.research-verdict__chips { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; max-width: 250px; }
.verdict-chip { display: inline-flex; max-width: 100%; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid var(--evo-border); border-radius: 999px; color: var(--evo-muted); background: var(--evo-surface); font-size: 9px; line-height: 1.25; white-space: nowrap; }
.verdict-chip--status { color: var(--evo-accent); border-color: color-mix(in srgb, var(--evo-accent) 38%, var(--evo-border)); }
.research-verdict--review .verdict-chip--status { color: var(--evo-warning); border-color: color-mix(in srgb, var(--evo-warning) 42%, var(--evo-border)); }
.verdict-chip--status i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }
.verdict-chip--boundary { overflow: hidden; color: var(--evo-warning); border-color: color-mix(in srgb, var(--evo-warning) 32%, var(--evo-border)); text-overflow: ellipsis; }
.study-facts { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 8px 0 10px; padding: 9px 12px; border: 1px solid var(--evo-border-soft); border-radius: 8px; color: var(--evo-faint); background: var(--evo-surface-strong); font-size: 10px; }
.study-facts span { display: flex; gap: 5px; align-items: center; }
.study-facts b { color: var(--evo-accent); font-size: 12px; }
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.chart-grid--hero { grid-template-columns: 1.65fr 1fr; }
.chart-card, .candidate-card { overflow: hidden; border: 1px solid var(--evo-border); border-radius: 9px; background: var(--evo-panel); box-shadow: 0 1px 2px var(--evo-shadow); }
.chart-title { display: flex; align-items: center; justify-content: space-between; height: 42px; padding: 0 13px; border-bottom: 1px solid var(--evo-border-soft); }
.chart-title strong { color: var(--evo-text); font-size: 12px; }
.chart-title span { color: var(--evo-faint); font-size: 10px; }
.chart { height: 220px; }
.chart--hero { height: 270px; }
.candidate-card { margin-top: 10px; }
.candidate-table__head, .candidate-table__row { display: grid; grid-template-columns: 45px 75px minmax(240px, 1fr) 85px 100px 100px; align-items: center; gap: 12px; min-height: 38px; padding: 0 13px; border-bottom: 1px solid var(--evo-border-soft); color: var(--evo-muted); font-size: 11px; }
.candidate-table__head { color: var(--evo-faint); background: var(--evo-surface-strong); }
.candidate-table__row strong { color: var(--evo-accent); }
.candidate-table__row code { overflow: hidden; color: var(--evo-muted); text-overflow: ellipsis; white-space: nowrap; }
.fold-table { overflow-x: auto; }
.fold-table__head, .fold-table__row { display: grid; grid-template-columns: 45px 1.25fr 1.25fr 95px 105px 85px; align-items: center; gap: 12px; min-width: 780px; min-height: 38px; padding: 0 13px; border-bottom: 1px solid var(--evo-border-soft); color: var(--evo-muted); font-size: 11px; }
.fold-table__head { color: var(--evo-faint); background: var(--evo-surface-strong); }
.fold-table__row strong { color: var(--evo-heading); }
.fold-table__row .negative { color: var(--evo-danger); }
.evolution-validation { padding-bottom: 0; }
.history-title { flex: 0 0 auto; }
.history-title /deep/ .ant-btn { margin-left: auto; padding: 0; color: var(--evo-faint); }
.history-list { flex: 0 1 300px; min-height: 86px; overflow: auto; padding: 8px; border-bottom: 1px solid var(--evo-border); }
.history-empty { padding: 20px 8px; color: var(--evo-disabled); font-size: 11px; text-align: center; }
.history-item { width: 100%; padding: 9px; border: 1px solid transparent; border-radius: 8px; color: var(--evo-faint); background: transparent; text-align: left; cursor: pointer; }
.history-item + .history-item { margin-top: 4px; }
.history-item:hover, .history-item--active { border-color: color-mix(in srgb, var(--evo-accent) 42%, var(--evo-border)); background: color-mix(in srgb, var(--evo-accent) 7%, var(--evo-panel)); }
.history-item__top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.history-item strong { overflow: hidden; color: var(--evo-text); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.history-item > span:not(.history-item__top), .history-item small { display: block; margin-top: 3px; overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.history-item .history-item__failure { display: -webkit-box; overflow: hidden; color: var(--evo-danger); line-height: 1.35; white-space: normal; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.job-status { flex: 0 0 auto; font-size: 9px; font-style: normal; }
.job-status--running, .job-status--queued, .job-status--succeeded { color: var(--evo-accent); }
.job-status--failed, .job-status--cancelled { color: var(--evo-danger); }
.validation-divider { display: flex; flex: 0 0 auto; gap: 8px; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--evo-border); color: var(--evo-accent); font-size: 11px; }
.validation-divider strong { color: var(--evo-text); }
.validation-scroll { min-height: 0; overflow: auto; flex: 1; }
.deployment-decision { margin: 14px; padding: 13px; border: 1px solid color-mix(in srgb, var(--evo-accent) 42%, var(--evo-border)); border-radius: 9px; background: color-mix(in srgb, var(--evo-accent) 8%, var(--evo-panel)); }
.deployment-decision > span { display: flex; gap: 6px; align-items: center; color: var(--evo-accent); font-size: 10px; font-weight: 700; }
.deployment-decision strong { display: block; margin-top: 7px; color: var(--evo-heading); font-size: 14px; }
.deployment-decision p { margin: 6px 0 0; color: var(--evo-muted); font-size: 10px; line-height: 1.5; }
.deployment-decision--review { border-color: color-mix(in srgb, var(--evo-warning) 50%, var(--evo-border)); background: color-mix(in srgb, var(--evo-warning) 7%, var(--evo-panel)); }
.deployment-decision--review > span { color: var(--evo-warning); }
.validation-score { display: grid; grid-template-columns: 58px 1fr; gap: 12px; align-items: center; margin: 14px; padding: 14px; border: 1px solid color-mix(in srgb, var(--evo-accent) 42%, var(--evo-border)); border-radius: 9px; background: linear-gradient(135deg, color-mix(in srgb, var(--evo-accent) 11%, var(--evo-panel)), var(--evo-surface)); box-shadow: inset 3px 0 0 var(--evo-accent); }
.validation-score > span { display: grid; place-items: center; width: 48px; height: 48px; border: 1px solid currentColor; border-radius: 50%; color: var(--evo-accent); font-size: 27px; font-weight: 800; }
.validation-score > div { min-width: 0; }
.validation-score strong { display: block; color: var(--evo-heading); font-size: 25px; line-height: 1.1; }
.validation-score strong small { margin-left: 2px; color: var(--evo-faint); font-size: 10px; font-weight: 500; }
.validation-score p { margin: 5px 0 0; color: var(--evo-muted); font-size: 9px; }
.validation-score--c { border-color: color-mix(in srgb, var(--evo-warning) 55%, var(--evo-border)); box-shadow: inset 3px 0 0 var(--evo-warning); }
.validation-score--c > span { color: var(--evo-warning); }
.validation-score--d { border-color: color-mix(in srgb, var(--evo-danger) 48%, var(--evo-border)); background: linear-gradient(135deg, color-mix(in srgb, var(--evo-danger) 9%, var(--evo-panel)), var(--evo-surface)); box-shadow: inset 3px 0 0 var(--evo-danger); }
.validation-score--d > span { color: var(--evo-danger); }
.validation-card { margin: 0 14px 9px; padding: 12px; border: 1px solid var(--evo-border); border-radius: 9px; background: var(--evo-surface); }
.validation-card > div { display: flex; gap: 8px; align-items: center; color: var(--evo-muted); }
.validation-card > div i { color: var(--evo-accent); }
.validation-card b { display: block; margin-top: 9px; color: var(--evo-heading); font-size: 20px; font-variant-numeric: tabular-nums; }
.validation-card p { margin: 4px 0 0; color: var(--evo-faint); font-size: 10px; line-height: 1.5; }
.best-params { margin: 14px; padding-top: 12px; border-top: 1px solid var(--evo-border); }
.best-params > strong { display: block; margin-bottom: 8px; color: var(--evo-text); }
.best-params div { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--evo-border-soft); }
.best-params code { color: var(--evo-muted); }
.best-params b { color: var(--evo-accent); }
.validation-placeholder { display: grid; grid-template-columns: 24px minmax(0, 1fr); align-items: start; gap: 10px; margin: 14px; padding: 13px 14px; border: 1px solid var(--evo-border); border-radius: 8px; color: var(--evo-muted); background: var(--evo-surface); text-align: left; }
.validation-placeholder i { margin-top: 2px; color: var(--evo-accent); font-size: 17px; }
.validation-placeholder p { margin: 0; font-size: 11px; line-height: 1.55; }
.evolution-failure .empty-icon { border-color: color-mix(in srgb, var(--evo-danger) 45%, var(--evo-border)); color: var(--evo-danger); background: color-mix(in srgb, var(--evo-danger) 8%, var(--evo-panel)); }
.failure-facts { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 14px; }
.failure-facts span { padding: 7px 10px; border: 1px solid var(--evo-border); border-radius: 3px; color: var(--evo-muted); background: var(--evo-surface); font-size: 10px; }
.failure-facts b { margin-right: 4px; color: var(--evo-heading); font-size: 13px; }
@media (max-width: 1500px) { .evolution-shell { grid-template-columns: 310px minmax(620px, 1fr) 240px; }.metric-grid { grid-template-columns: repeat(3, 1fr); }.research-verdict { grid-template-columns: 36px minmax(0, 1fr); }.research-verdict__chips { grid-column: 2; max-width: none; flex-direction: row; align-items: center; } }
@media (max-width: 1280px) { .evolution-shell { grid-template-columns: 310px minmax(0, 1fr); }.evolution-validation { display: none; }.chart-grid, .chart-grid--hero { grid-template-columns: 1fr; } }
</style>
