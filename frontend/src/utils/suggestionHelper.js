/**
 * Intelligent context-aware follow-up suggestions for DCE Assistant.
 *
 * Dynamically analyzes the user prompt and active data source to recommend
 * relevant next queries, drill-downs, exception analysis, and related metrics
 * instead of returning static options.
 */

// ============================================================================
// SUGGESTION POOLS BY SOURCE & TOPIC
// ============================================================================

const GPO_SUGGESTIONS = [
  // Batches & Overall Status
  {
    id: 'gpo_batches_failed',
    title: 'Batches with a failed validation stage',
    icon: '⚠️',
    query: 'Which batches have a failed validation stage?',
    tags: ['batch', 'batches', 'failed', 'failure', 'error', 'status', 'job_status', 'validation', 'today', 'processed', 'customer'],
    category: 'batches'
  },
  {
    id: 'gpo_batches_summary',
    title: 'Batch summary by job status',
    icon: '📊',
    query: 'Show summary count of batches grouped by job status',
    tags: ['batch', 'batches', 'summary', 'status', 'job_status', 'in-progress', 'completed', 'failed', 'count', 'today'],
    category: 'batches'
  },
  {
    id: 'gpo_batches_stage_status',
    title: 'Per-stage status for the latest batches',
    icon: '📋',
    query: 'Show the per-stage validation status for the 10 most recent batches',
    tags: ['batch', 'batches', 'stage', 'per-stage', 'latest', 'recent', 'validation', 'all', 'today'],
    category: 'batches'
  },
  {
    id: 'gpo_batches_awaiting_output',
    title: 'Batches awaiting output generation',
    icon: '📤',
    query: 'Show batches that are fully validated but have no output generated yet',
    tags: ['batch', 'batches', 'output', 'output_status', 'pending', 'generation', 'file', 'completed', 'today'],
    category: 'batches'
  },
  {
    id: 'gpo_batches_in_progress',
    title: 'Batches currently in-progress',
    icon: '⏳',
    query: 'Show all customer batches currently in-progress',
    tags: ['batch', 'batches', 'in-progress', 'running', 'pending', 'active', 'today'],
    category: 'batches'
  },
  {
    id: 'gpo_batches_input_files',
    title: 'Input files with stage failure details',
    icon: '📁',
    query: 'List input file names where any validation stage failed',
    tags: ['file', 'file_name', 'input', 'files', 'failed', 'stage', 'batch', 'batches'],
    category: 'batches'
  },

  // HIN Validation
  {
    id: 'gpo_hin_match_types',
    title: 'HIN match outcomes by match type',
    icon: '🔗',
    query: 'Show HIN match outcomes grouped by match type for the most recent batch',
    tags: ['hin', 'hin_status', 'match', 'match_type', 'health industry number', 'validation', 'outcomes'],
    category: 'hin'
  },
  {
    id: 'gpo_hin_failed',
    title: 'Records with failed or pending HIN status',
    icon: '❌',
    query: 'List customer records where HIN status is Failed or Pending',
    tags: ['hin', 'hin_status', 'failed', 'pending', 'error', 'unmatched', 'records'],
    category: 'hin'
  },
  {
    id: 'gpo_hin_vs_dea',
    title: 'Compare HIN status with DEA status',
    icon: '⚖️',
    query: 'Compare HIN validation status versus DEA status across customer records',
    tags: ['hin', 'dea', 'compare', 'validation', 'status', 'cross'],
    category: 'hin'
  },

  // DEA Validation
  {
    id: 'gpo_dea_status',
    title: 'Customer records where DEA validation failed',
    icon: '🚫',
    query: 'List all customer records where DEA status is Failed',
    tags: ['dea', 'dea_status', 'drug enforcement', 'failed', 'invalid', 'validation', 'license'],
    category: 'dea'
  },
  {
    id: 'gpo_dea_active_expired',
    title: 'Active vs expired DEA verification',
    icon: '🪪',
    query: 'Show customer records with active versus expired DEA numbers',
    tags: ['dea', 'expired', 'active', 'license', 'practitioner', 'schedule'],
    category: 'dea'
  },

  // Class of Trade (COT)
  {
    id: 'gpo_cot_discrepancies',
    title: 'Class of trade discrepancies',
    icon: '🏷️',
    query: 'Show records where the corrected class of trade differs from the submitted one',
    tags: ['cot', 'cot_status', 'class of trade', 'trade', 'discrepancies', 'discrepancy', 'corrected', 'submitted'],
    category: 'cot'
  },
  {
    id: 'gpo_cot_breakdown',
    title: 'Customer distribution by Class of Trade',
    icon: '🏢',
    query: 'Show distribution of customers grouped by validated Class of Trade',
    tags: ['cot', 'class of trade', 'trade', 'hospital', 'clinic', 'pharmacy', 'distribution', 'group'],
    category: 'cot'
  },
  {
    id: 'gpo_cot_failed',
    title: 'Records where COT validation failed',
    icon: '⚠️',
    query: 'List customer records where COT status is Failed or In-Progress',
    tags: ['cot', 'cot_status', 'failed', 'in-progress', 'trade', 'validation'],
    category: 'cot'
  },

  // HRSA 340B Validation
  {
    id: 'gpo_hrsa_status',
    title: 'HRSA 340B entity validation status',
    icon: '🏛️',
    query: 'Show HRSA validation status and 340B eligibility breakdown',
    tags: ['hrsa', 'hrsa_status', '340b', 'covered entity', 'eligibility', 'validation'],
    category: 'hrsa'
  },
  {
    id: 'gpo_hrsa_ineligible',
    title: 'Records flagged as ineligible for HRSA',
    icon: '⚠️',
    query: 'List customer records where HRSA status is Failed or Ineligible',
    tags: ['hrsa', 'hrsa_status', 'ineligible', 'failed', '340b', 'disqualified'],
    category: 'hrsa'
  },

  // USPS Address Validation
  {
    id: 'gpo_usps_failed',
    title: 'USPS address standardization failures',
    icon: '📮',
    query: 'Show records where USPS address standardization failed or needs review',
    tags: ['usps', 'usps_status', 'address', 'postal', 'zip', 'standardization', 'failed'],
    category: 'usps'
  },
  {
    id: 'gpo_usps_by_state',
    title: 'Address validation outcomes by state',
    icon: '📍',
    query: 'Show USPS validation success rate grouped by state',
    tags: ['usps', 'address', 'state', 'outcomes', 'geography', 'zip'],
    category: 'usps'
  },

  // Membership & Roster
  {
    id: 'gpo_roster_membership',
    title: 'Eligible customer roster by GPO tier',
    icon: '👥',
    query: 'Show eligible customer roster grouped by tier and contract',
    tags: ['roster', 'membership', 'member', 'member_status', 'eligible customer', 'tier', 'contract'],
    category: 'membership'
  },
  {
    id: 'gpo_contracts_active',
    title: 'Active structured contracts and customer counts',
    icon: '📑',
    query: 'List active structured contracts and customer count per contract',
    tags: ['contract', 'structured contract', 'pricing', 'contracts', 'tier', 'agreements'],
    category: 'membership'
  },

  // Roles, Permissions & Security / Audit
  {
    id: 'gpo_roles_crud',
    title: 'Roles and their CRUD permissions',
    icon: '🔐',
    query: 'List roles with their view, add, edit and delete permissions',
    tags: ['role', 'roles', 'permission', 'permissions', 'crud', 'access', 'security', 'privilege', 'view', 'edit', 'delete'],
    category: 'security'
  },
  {
    id: 'gpo_user_audit',
    title: 'Recent user audit trail activity',
    icon: '📜',
    query: 'Show the recent user activity audit trail and change logs',
    tags: ['audit', 'audit trail', 'user', 'activity', 'log', 'logs', 'history', 'changes'],
    category: 'security'
  }
];

const COMMERCIAL_SUGGESTIONS = [
  // UC1: Leakage Signals & Claims
  {
    id: 'comm_leakage_state',
    title: 'Calculate leakage summary by state',
    icon: '📊',
    query: 'Calculate leakage summary grouped by state',
    tags: ['leakage', 'state', 'summary', 'geographic', 'region', 'calculate', 'physician', 'claims'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_top_physicians',
    title: 'Top 10 physician leakage records',
    icon: '📉',
    query: 'Show the top 10 physician leakage records',
    tags: ['leakage', 'physician', 'top', 'prescriber', 'doctor', 'records', 'highest'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_prior_auth',
    title: 'Claims rejected due to Prior Authorization',
    icon: '🚫',
    query: 'List all claims rejected due to prior authorization requirements',
    tags: ['claim', 'claims', 'rejected', 'rejection', 'prior authorization', 'prior auth', 'pa', 'leakage'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_govt_bypassed',
    title: 'Analyze government plans bypassed KPI',
    icon: '🏛️',
    query: 'Show government plans bypassed summary from compliance table',
    tags: ['compliance', 'government', 'govt', 'bypassed', 'kpi', 'plan', 'plans', 'compliance_table'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_high_rate',
    title: 'Prescribers with leakage > 50%',
    icon: '🔍',
    query: 'Find prescribers where leakage rate is greater than 50%',
    tags: ['prescribers', 'prescriber', 'leakage', 'rate', 'percentage', 'high', '50%'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_reverse_claims',
    title: 'Reverse claims analysis and leakage impact',
    icon: '🔄',
    query: 'Show reverse claims records and their estimated leakage financial impact',
    tags: ['reverse', 'reverse_claims', 'claims', 'claim', 'financial', 'impact', 'loss', 'amount'],
    category: 'leakage'
  },
  {
    id: 'comm_leakage_threshold_history',
    title: 'Threshold update history for leakage alerts',
    icon: '📈',
    query: 'Show recent threshold update history from leakage_history',
    tags: ['threshold', 'history', 'leakage_history', 'updates', 'alerts', 'rule'],
    category: 'leakage'
  },

  // UC2: Journey Orchestration & HCP Fatigue
  {
    id: 'comm_fatigue_high_score',
    title: 'Physicians with fatigue score above 45',
    icon: '⚡',
    query: 'List all physicians flagged with a digital fatigue score above 45',
    tags: ['fatigue', 'fatigue score', 'score', 'physicians', 'physician', 'doctor', 'hcp', 'high', '45', 'burnout'],
    category: 'fatigue'
  },
  {
    id: 'comm_fatigue_campaign_open_rate',
    title: 'Email open rate per campaign',
    icon: '📧',
    query: 'Show email open rate per campaign',
    tags: ['email', 'open rate', 'campaign', 'campaigns', 'marketing', 'engagement', 'click', 'rate'],
    category: 'fatigue'
  },
  {
    id: 'comm_fatigue_active_campaigns',
    title: 'High-fatigue HCPs in active campaigns',
    icon: '🎯',
    query: 'List high-fatigue HCPs who are currently in active marketing campaigns',
    tags: ['fatigue', 'active', 'campaign', 'campaigns', 'marketing', 'hcp', 'hcps', 'overloaded'],
    category: 'fatigue'
  },
  {
    id: 'comm_fatigue_by_specialty',
    title: 'Average fatigue score by specialty',
    icon: '📊',
    query: 'Show average fatigue score distribution across medical specialties',
    tags: ['fatigue', 'specialty', 'specialities', 'average', 'distribution', 'medical', 'oncology', 'cardiology'],
    category: 'fatigue'
  },
  {
    id: 'comm_fatigue_recent_logs',
    title: 'Recent engagement logs for fatigued HCPs',
    icon: '🔄',
    query: 'Show recent engagement logs for physicians with fatigue score above 40',
    tags: ['engagement', 'logs', 'fatigue', 'touchpoint', 'interaction', 'recent', 'channel'],
    category: 'fatigue'
  },
  {
    id: 'comm_fatigue_channel_breakdown',
    title: 'Channel engagement comparison',
    icon: '📱',
    query: 'Compare engagement response rates across Email, Rep Visits, and Digital channels',
    tags: ['channel', 'channels', 'email', 'rep visit', 'webinar', 'digital', 'multichannel'],
    category: 'fatigue'
  },

  // UC3: Voice Work Detail Manager & Rep Interactions
  {
    id: 'comm_work_rep_2006',
    title: 'Show work details for rep 2006',
    icon: '🎙️',
    query: 'Show work details for rep 2006',
    tags: ['rep', '2006', 'work detail', 'work_detail', 'sales rep', 'notes', 'rep_id'],
    category: 'work_detail'
  },
  {
    id: 'comm_work_needs_followup',
    title: 'List HCPs with status "Needs Follow-up"',
    icon: '📋',
    query: 'List HCPs managed by reps with status Needs Follow-up',
    tags: ['follow-up', 'followup', 'needs follow-up', 'status', 'pending', 'hcp', 'hcps', 'action'],
    category: 'work_detail'
  },
  {
    id: 'comm_work_recent_updates',
    title: 'Recent work detail history updates',
    icon: '📜',
    query: 'Show recent work detail history updates with rep names',
    tags: ['work detail', 'work_detail', 'history', 'updates', 'recent', 'audit', 'rep', 'doctor notes'],
    category: 'work_detail'
  },
  {
    id: 'comm_work_rep_interaction_counts',
    title: 'Sales reps with assigned HCP interaction counts',
    icon: '👥',
    query: 'List sales reps with their assigned HCP interaction counts',
    tags: ['rep', 'reps', 'sales rep', 'interaction', 'counts', 'workload', 'assigned', 'hcp'],
    category: 'work_detail'
  },
  {
    id: 'comm_work_recent_notes',
    title: '10 most recently updated doctor notes',
    icon: '🩺',
    query: 'Show the 10 most recently updated HCP work details',
    tags: ['doctor', 'notes', 'work detail', 'updated', 'recent', 'latest', 'hcp'],
    category: 'work_detail'
  },
  {
    id: 'comm_work_manager_hierarchy',
    title: 'Sales reps grouped by manager hierarchy',
    icon: '👔',
    query: 'List sales representatives grouped by manager ID with contact info',
    tags: ['manager', 'rep_master', 'hierarchy', 'directory', 'reps', 'sales rep', 'phone', 'email'],
    category: 'work_detail'
  },

  // UC4: Clinical Medicine Extraction
  {
    id: 'comm_clinical_top_tablets',
    title: 'Most frequently extracted tablets with dosages',
    icon: '💊',
    query: 'Show the most frequently extracted tablets with their dosages',
    tags: ['tablet', 'tablets', 'medicine', 'drug', 'dosage', 'dosages', 'frequently', 'clinical', 'extracted'],
    category: 'clinical'
  },
  {
    id: 'comm_clinical_completed_transcripts',
    title: 'Transcripts with completed extraction',
    icon: '📝',
    query: 'List clinical transcripts with extraction status Completed',
    tags: ['transcript', 'transcripts', 'completed', 'status', 'extraction', 'clinical'],
    category: 'clinical'
  },
  {
    id: 'comm_clinical_by_prescriber',
    title: 'Medicine extraction by Prescriber NPI',
    icon: '🩺',
    query: 'Show tablet extraction history grouped by Prescriber NPI',
    tags: ['prescriber_npi', 'prescriber', 'npi', 'tablet', 'medicine', 'hcp', 'extraction'],
    category: 'clinical'
  },
  {
    id: 'comm_clinical_twice_daily',
    title: 'Medicines with frequency "Twice Daily"',
    icon: '⏱️',
    query: 'List all extracted medicines with frequency Twice Daily',
    tags: ['frequency', 'twice daily', 'daily', 'dosage', 'medicine', 'tablet', 'schedule'],
    category: 'clinical'
  },
  {
    id: 'comm_clinical_guidance_notes',
    title: 'Tablets with clinical guidance notes',
    icon: '🏷️',
    query: 'Show tablet extractions with guidance messages and timestamps',
    tags: ['guidance', 'clinical', 'message', 'warning', 'safety', 'tablet', 'notes'],
    category: 'clinical'
  },
  {
    id: 'comm_clinical_failed_extractions',
    title: 'Transcripts with pending or failed extraction',
    icon: '⚠️',
    query: 'List clinical transcripts where extraction status is Failed or Pending',
    tags: ['failed', 'pending', 'transcript', 'error', 'unmapped', 'extraction'],
    category: 'clinical'
  },

  // UC5: Salesforce Sync Audit (Commercial DB)
  {
    id: 'comm_sync_audit_logs',
    title: 'Salesforce sync audit logs',
    icon: '☁️',
    query: 'Show Salesforce sync status and audit logs',
    tags: ['salesforce', 'sync', 'audit', 'logs', 'crm', 'salesforce_sync_log', 'status'],
    category: 'sync_audit'
  },
  {
    id: 'comm_sync_mapped_hcps',
    title: 'HCP records mapped with Salesforce ID',
    icon: '✅',
    query: 'List HCP records successfully mapped with Salesforce ID',
    tags: ['sf_id', 'mapped', 'salesforce', 'hcp', 'id', 'sync', 'synced'],
    category: 'sync_audit'
  },
  {
    id: 'comm_sync_failed',
    title: 'Check failed or pending CRM syncs',
    icon: '⚠️',
    query: 'Show any medicine extractions or HCP records with sync status Failed',
    tags: ['failed', 'pending', 'sync', 'crm', 'salesforce', 'retry', 'error'],
    category: 'sync_audit'
  }
];

const SALESFORCE_CRM_SUGGESTIONS = [
  {
    id: 'sf_doctors_with_reps',
    title: 'Doctors with their assigned sales rep',
    icon: '🩺',
    query: 'List all doctors with their assigned sales representative details',
    tags: ['doctor', 'doctors', 'sales rep', 'rep', 'assigned', 'rep_details__c', 'doctor__c'],
    category: 'doctors'
  },
  {
    id: 'sf_doctors_by_state',
    title: 'Doctors by practice state',
    icon: '📍',
    query: 'Show all doctors grouped by practice state',
    tags: ['state', 'practice state', 'doctor', 'doctors', 'geography', 'location'],
    category: 'doctors'
  },
  {
    id: 'sf_doctors_inprogress',
    title: 'In-progress doctors with speciality',
    icon: '⏳',
    query: 'List all In-Progress doctors with their speciality and state',
    tags: ['in-progress', 'in progress', 'speciality', 'specialty', 'doctor', 'doctors', 'status'],
    category: 'doctors'
  },
  {
    id: 'sf_doctors_completed',
    title: 'Completed doctors by speciality',
    icon: '✅',
    query: 'List all Completed doctors with their speciality and practice state',
    tags: ['completed', 'speciality', 'specialty', 'doctor', 'doctors', 'onboarded'],
    category: 'doctors'
  },
  {
    id: 'sf_reps_contact_directory',
    title: 'Sales reps with email and phone',
    icon: '📇',
    query: 'Show sales representatives along with their email and phone',
    tags: ['sales rep', 'rep', 'reps', 'email', 'phone', 'contact', 'directory', 'rep_details__c'],
    category: 'reps'
  },
  {
    id: 'sf_doctors_license_phone',
    title: 'Doctors with state license and phone',
    icon: '🪪',
    query: 'Show doctors with their state license and phone number',
    tags: ['license', 'state license', 'phone', 'doctor', 'doctors', 'contact', 'verification'],
    category: 'doctors'
  },
  {
    id: 'sf_reps_doctor_count',
    title: 'Sales reps with total assigned doctor counts',
    icon: '👥',
    query: 'Show sales representatives along with the count of doctors assigned to them',
    tags: ['rep', 'reps', 'sales rep', 'count', 'assigned', 'doctors', 'workload'],
    category: 'reps'
  },
  {
    id: 'sf_doctors_specialty_breakdown',
    title: 'Doctor count grouped by medical specialty',
    icon: '📊',
    query: 'Show total count of doctors grouped by medical speciality',
    tags: ['speciality', 'specialty', 'breakdown', 'count', 'distribution', 'doctors'],
    category: 'doctors'
  }
];

// Map pool by source identifier
const POOLS_BY_SOURCE = {
  mysql_gpo: GPO_SUGGESTIONS,
  salesforce: SALESFORCE_CRM_SUGGESTIONS,
  mysql_primary: COMMERCIAL_SUGGESTIONS,
};

// ============================================================================
// HELPER FUNCTIONS & RELEVANCE SCORING
// ============================================================================

function normalizeSourceId(source) {
  if (!source) return 'mysql_primary';
  const s = String(source).toLowerCase();
  if (s.includes('gpo') || s.includes('memcot')) return 'mysql_gpo';
  if (s.includes('salesforce') || s.includes('crm')) return 'salesforce';
  return 'mysql_primary';
}

/**
 * Tokenizes text into lowercase normalized keyword tokens, stripping punctuation.
 */
function tokenize(text) {
  if (!text || typeof text !== 'string') return [];
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s_]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 1);
}

/**
 * Calculates word overlap / Jaccard similarity between two texts.
 */
function calculateSimilarity(textA, textB) {
  const tokensA = new Set(tokenize(textA));
  const tokensB = new Set(tokenize(textB));
  if (tokensA.size === 0 || tokensB.size === 0) return 0;
  
  let intersection = 0;
  for (const token of tokensA) {
    if (tokensB.has(token)) intersection++;
  }
  
  const union = new Set([...tokensA, ...tokensB]).size;
  return union > 0 ? intersection / union : 0;
}

/**
 * Scores a candidate suggestion against the user prompt.
 */
function scoreSuggestion(item, promptText, promptTokens, promptLower) {
  let score = 0;
  const itemTokens = new Set(tokenize(`${item.title} ${item.query}`));
  const tags = item.tags || [];

  // Exact query / prompt deduplication check:
  // If prompt is virtually identical to suggestion query or title, heavily penalize so user doesn't get what they just asked
  const queryLower = item.query.toLowerCase();
  const titleLower = item.title.toLowerCase();
  const simQuery = calculateSimilarity(promptLower, queryLower);
  const simTitle = calculateSimilarity(promptLower, titleLower);

  if (
    promptLower.includes(queryLower) ||
    queryLower.includes(promptLower) ||
    promptLower.includes(titleLower) ||
    titleLower.includes(promptLower) ||
    simQuery > 0.55 ||
    simTitle > 0.6
  ) {
    return -100;
  }

  // 1. Tag matching: High precision matching for domain concepts
  for (const tag of tags) {
    const tagLower = tag.toLowerCase();
    if (tagLower.includes(' ')) {
      // Multi-word phrase matching (e.g. "prior auth", "class of trade", "open rate")
      if (promptLower.includes(tagLower)) {
        score += 15;
      }
    } else {
      if (promptTokens.includes(tagLower)) {
        score += 8;
      } else if (promptLower.includes(tagLower)) {
        score += 4;
      }
    }
  }

  // 2. Token overlap with title & query
  for (const pToken of promptTokens) {
    if (itemTokens.has(pToken)) {
      score += 4;
    }
  }

  // 3. Category/Context-specific synergy & drill-down incentives
  // If user asked an overview batch prompt, boost drill-down batch checks
  if (
    (promptLower.includes('batch') || promptLower.includes('batches') || promptLower.includes('today')) &&
    item.category === 'batches'
  ) {
    score += 10;
  }

  // If user asked about HIN
  if (
    (promptLower.includes('hin') || promptLower.includes('health industry')) &&
    item.category === 'hin'
  ) {
    score += 20;
  }

  // If user asked about DEA
  if (
    (promptLower.includes('dea') || promptLower.includes('drug enforcement')) &&
    item.category === 'dea'
  ) {
    score += 20;
  }

  // If user asked about Class of Trade (COT)
  if (
    (promptLower.includes('cot') || promptLower.includes('class of trade') || promptLower.includes('trade')) &&
    item.category === 'cot'
  ) {
    score += 20;
  }

  // If user asked about HRSA 340B
  if (
    (promptLower.includes('hrsa') || promptLower.includes('340b')) &&
    item.category === 'hrsa'
  ) {
    score += 20;
  }

  // If user asked about USPS / Address
  if (
    (promptLower.includes('usps') || promptLower.includes('address') || promptLower.includes('zip')) &&
    item.category === 'usps'
  ) {
    score += 20;
  }

  // If user asked about Roles / Permissions / Security
  if (
    (promptLower.includes('role') || promptLower.includes('permission') || promptLower.includes('crud') || promptLower.includes('user') || promptLower.includes('audit')) &&
    item.category === 'security'
  ) {
    score += 20;
  }

  // If user asked about Leakage / Claims / Rejections (UC1)
  if (
    (promptLower.includes('leakage') || promptLower.includes('claim') || promptLower.includes('rejection') || promptLower.includes('bypassed') || promptLower.includes('prior auth')) &&
    item.category === 'leakage'
  ) {
    score += 15;
  }

  // If user asked about Fatigue / Campaigns (UC2)
  if (
    (promptLower.includes('fatigue') || promptLower.includes('campaign') || promptLower.includes('open rate') || promptLower.includes('burnout')) &&
    item.category === 'fatigue'
  ) {
    score += 15;
  }

  // If user asked about Rep notes / Work details (UC3)
  if (
    (promptLower.includes('work detail') || promptLower.includes('work_detail') || promptLower.includes('rep') || promptLower.includes('note') || promptLower.includes('interaction')) &&
    item.category === 'work_detail'
  ) {
    score += 15;
  }

  // If user asked about Clinical tablets / Transcripts (UC4)
  if (
    (promptLower.includes('tablet') || promptLower.includes('medicine') || promptLower.includes('drug') || promptLower.includes('transcript') || promptLower.includes('dosage') || promptLower.includes('clinical')) &&
    item.category === 'clinical'
  ) {
    score += 15;
  }

  // If user asked about Salesforce sync audit (UC5)
  if (
    (promptLower.includes('sync') || promptLower.includes('sf_id') || promptLower.includes('crm') || promptLower.includes('audit log')) &&
    item.category === 'sync_audit'
  ) {
    score += 15;
  }

  return score;
}

/**
 * Main function to generate dynamic, prompt-related follow-up suggestions.
 *
 * @param {string} userPrompt - The question that produced the answer.
 * @param {string} sourceId   - The data source that answered it ('mysql_primary', 'mysql_gpo', 'salesforce').
 * @param {number} limit      - Max chips to return (default: 4).
 * @returns {Array<{title: string, icon: string, query: string}>}
 */
export function getFollowUpSuggestions(userPrompt, sourceId, limit = 4) {
  const normalizedSource = normalizeSourceId(sourceId);
  const pool = POOLS_BY_SOURCE[normalizedSource] || COMMERCIAL_SUGGESTIONS;

  if (!userPrompt || typeof userPrompt !== 'string' || !userPrompt.trim()) {
    // Return the top standard exploratory suggestions for this source
    return pool.slice(0, limit);
  }

  const promptLower = userPrompt.trim().toLowerCase();
  const promptTokens = tokenize(promptLower);

  // Score every item in the pool
  const scoredItems = pool
    .map((item) => ({
      ...item,
      _score: scoreSuggestion(item, userPrompt, promptTokens, promptLower)
    }))
    .filter((item) => item._score > -50); // Exclude duplicates / heavily penalized items

  // Sort descending by relevance score
  scoredItems.sort((a, b) => b._score - a._score);

  // Select top distinct suggestions
  const selected = [];
  const seenCategories = new Set();

  // First pass: take highest scoring items, ensuring topic variety if scores are close
  for (const item of scoredItems) {
    if (selected.length >= limit) break;
    selected.push(item);
    seenCategories.add(item.category);
  }

  // If we didn't get enough items due to deduplication, fill up with other available items from the pool
  if (selected.length < limit) {
    for (const item of pool) {
      if (selected.length >= limit) break;
      if (!selected.some((s) => s.id === item.id) && !promptLower.includes(item.query.toLowerCase())) {
        selected.push(item);
      }
    }
  }

  return selected.slice(0, limit).map(({ title, icon, query }) => ({
    title,
    icon,
    query
  }));
}
