const SUGGESTIONS_BY_DOMAIN = {
  leakage: [
    {
      title: 'Calculate leakage summary by state',
      icon: '📊',
      query: 'Calculate leakage summary grouped by state'
    },
    {
      title: 'Top 10 physician leakage records',
      icon: '📉',
      query: 'Show the top 10 physician leakage records'
    },
    {
      title: 'Claims rejected due to Prior Authorization',
      icon: '🚫',
      query: 'List all claims rejected due to prior authorization requirements'
    },
    {
      title: 'Analyze government plans bypassed KPI',
      icon: '🏛️',
      query: 'Show government plans bypassed summary from compliance table'
    },
    {
      title: 'Prescribers with leakage > 50%',
      icon: '🔍',
      query: 'Find prescribers where leakage rate is greater than 50%'
    }
  ],
  fatigue: [
    {
      title: 'Physicians with fatigue score above 45',
      icon: '⚡',
      query: 'List all physicians flagged with a digital fatigue score above 45'
    },
    {
      title: 'Email open rate per campaign',
      icon: '📧',
      query: 'Show email open rate per campaign'
    },
    {
      title: 'High-fatigue HCPs in active campaigns',
      icon: '🎯',
      query: 'List high-fatigue HCPs who are currently in active marketing campaigns'
    },
    {
      title: 'Average fatigue score by specialty',
      icon: '📊',
      query: 'Show average fatigue score distribution across medical specialties'
    },
    {
      title: 'Recent engagement logs for fatigued HCPs',
      icon: '🔄',
      query: 'Show recent engagement logs for physicians with fatigue score above 40'
    }
  ],
  work_detail: [
    {
      title: 'Show work details for rep 2006',
      icon: '🎙️',
      query: 'Show work details for rep 2006'
    },
    {
      title: 'List HCPs with status "Needs Follow-up"',
      icon: '📋',
      query: 'List HCPs managed by reps with status Needs Follow-up'
    },
    {
      title: 'Recent work detail history updates',
      icon: '📜',
      query: 'Show recent work detail history updates with rep names'
    },
    {
      title: 'Sales reps with assigned HCP interaction counts',
      icon: '👥',
      query: 'List sales reps with their assigned HCP interaction counts'
    },
    {
      title: '10 most recently updated doctor notes',
      icon: '🩺',
      query: 'Show the 10 most recently updated HCP work details'
    }
  ],
  clinical: [
    {
      title: 'Most frequently extracted tablets with dosages',
      icon: '💊',
      query: 'Show the most frequently extracted tablets with their dosages'
    },
    {
      title: 'Transcripts with completed extraction',
      icon: '📝',
      query: 'List clinical transcripts with extraction status Completed'
    },
    {
      title: 'Medicine extraction by Prescriber NPI',
      icon: '🩺',
      query: 'Show tablet extraction history grouped by Prescriber NPI'
    },
    {
      title: 'Medicines with frequency "Twice Daily"',
      icon: '⏱️',
      query: 'List all extracted medicines with frequency Twice Daily'
    },
    {
      title: 'Tablets with clinical guidance notes',
      icon: '🏷️',
      query: 'Show tablet extractions with guidance messages and timestamps'
    }
  ],
  // NOTE: these are Commercial DB (UC5) prompts about sync-audit tables
  // (salesforce_sync_log, hcp_master_details.sf_id) — NOT the Salesforce CRM
  // source. Named 'salesforce' previously, which made it easy to offer these
  // as follow-ups to a Salesforce answer and jump database without meaning to.
  sync_audit: [
    {
      title: 'Salesforce sync audit logs',
      icon: '☁️',
      query: 'Show Salesforce sync status and audit logs'
    },
    {
      title: 'HCP records mapped with Salesforce ID',
      icon: '✅',
      query: 'List HCP records successfully mapped with Salesforce ID'
    },
    {
      title: 'Check failed or pending CRM syncs',
      icon: '⚠️',
      query: 'Show any medicine extractions or HCP records with sync status Failed'
    }
  ],
  // Genuine Salesforce CRM prompts — these query Doctor__c / Rep_Details__c.
  salesforce_crm: [
    {
      title: 'Doctors with their assigned sales rep',
      icon: '🩺',
      query: 'List all doctors with their assigned sales representative details'
    },
    {
      title: 'Doctors by practice state',
      icon: '📍',
      query: 'Show all doctors grouped by practice state'
    },
    {
      title: 'In-progress doctors with speciality',
      icon: '⏳',
      query: 'List all In-Progress doctors with their speciality and state'
    },
    {
      title: 'Sales reps with email and phone',
      icon: '📇',
      query: 'Show sales representatives along with their email and phone'
    },
    {
      title: 'Doctors with their state licence',
      icon: '🪪',
      query: 'Show doctors with their state license and phone number'
    },
    {
      title: 'Completed doctors by speciality',
      icon: '✅',
      query: 'List all Completed doctors with their speciality and practice state'
    }
  ],
  gpo: [
    {
      title: 'Batches with a failed validation stage',
      icon: '⚠️',
      query: 'Which batches have a failed validation stage?'
    },
    {
      title: 'Per-stage status for the latest batches',
      icon: '📋',
      query: 'Show the per-stage validation status for the 10 most recent batches'
    },
    {
      title: 'HIN match outcomes by match type',
      icon: '🔗',
      query: 'Show HIN match outcomes grouped by match type for the most recent batch'
    },
    {
      title: 'Batches awaiting output generation',
      icon: '📤',
      query: 'Show batches that are fully validated but have no output generated yet'
    },
    {
      title: 'Class of trade discrepancies',
      icon: '🏷️',
      query: 'Show records where the corrected class of trade differs from the submitted one'
    },
    {
      title: 'Roles and their CRUD permissions',
      icon: '🔐',
      query: 'List roles with their view, add, edit and delete permissions'
    }
  ],
  general: [
    {
      title: 'Top 10 physician leakage records',
      icon: '📉',
      query: 'Show the top 10 physician leakage records'
    },
    {
      title: 'Physicians with fatigue score above 45',
      icon: '⚡',
      query: 'List all physicians flagged with a digital fatigue score above 45'
    },
    {
      title: 'Leakage percentage summary by state',
      icon: '📊',
      query: 'Calculate leakage summary grouped by state'
    },
    {
      title: 'Email open rate per campaign',
      icon: '📧',
      query: 'Show email open rate per campaign'
    },
    {
      title: 'Work details for rep 2006',
      icon: '🎙️',
      query: 'Show work details for rep 2006'
    }
  ]
};

/**
 * Which suggestion groups each data source can actually answer.
 *
 * A follow-up chip must never silently move the conversation to a different
 * database: the chips read as "more of this", and a Commercial DB question
 * offered under a Salesforce answer looks like a routing mistake when the user
 * clicks it. Groups are therefore scoped to the source that answered.
 */
const DOMAINS_BY_SOURCE = {
  mysql_primary: ['leakage', 'fatigue', 'work_detail', 'clinical', 'sync_audit', 'general'],
  mysql_gpo: ['gpo'],
  salesforce: ['salesforce_crm'],
};

const DEFAULT_DOMAIN_BY_SOURCE = {
  mysql_primary: 'general',
  mysql_gpo: 'gpo',
  salesforce: 'salesforce_crm',
};

/**
 * @param userPrompt the question that produced the answer these chips sit under
 * @param sourceId   the data source that answered it (message.source_id).
 *                   Omitted -> legacy behaviour, keyword matching across all
 *                   Commercial DB groups.
 */
export function getFollowUpSuggestions(userPrompt, sourceId) {
  const allowed = DOMAINS_BY_SOURCE[sourceId];
  const sourceDefault = DEFAULT_DOMAIN_BY_SOURCE[sourceId] || 'general';

  // A source with exactly one group has nothing to disambiguate.
  if (allowed && allowed.length === 1) {
    return (SUGGESTIONS_BY_DOMAIN[allowed[0]] || SUGGESTIONS_BY_DOMAIN.general).slice(0, 4);
  }

  if (!userPrompt || typeof userPrompt !== 'string') {
    return (SUGGESTIONS_BY_DOMAIN[sourceDefault] || SUGGESTIONS_BY_DOMAIN.general).slice(0, 4);
  }

  const lower = userPrompt.toLowerCase();
  let domain = sourceDefault;

  // GPO validation vocabulary is checked first: it is the most distinctive of
  // the groups, and several of its terms ('batch', 'validation', 'output')
  // would otherwise be swallowed by the broader commercial-domain matches.
  if (
    lower.includes('gpo') ||
    lower.includes('batch') ||
    lower.includes(' hin') ||
    lower.startsWith('hin') ||
    lower.includes('dea') ||
    lower.includes('hrsa') ||
    lower.includes('usps') ||
    lower.includes('class of trade') ||
    lower.includes('roster') ||
    lower.includes('membership') ||
    lower.includes('eligible customer') ||
    lower.includes('structured contract') ||
    lower.includes('permission') ||
    lower.includes('audit trail')
  ) {
    domain = 'gpo';
  } else if (
    lower.includes('leakage') ||
    lower.includes('claim') ||
    lower.includes('rejection') ||
    lower.includes('bypassed') ||
    lower.includes('compliance') ||
    lower.includes('plan')
  ) {
    domain = 'leakage';
  } else if (
    lower.includes('fatigue') ||
    lower.includes('engagement') ||
    lower.includes('campaign') ||
    lower.includes('open rate') ||
    lower.includes('channel') ||
    lower.includes('burnout')
  ) {
    domain = 'fatigue';
  } else if (
    lower.includes('rep') ||
    lower.includes('work detail') ||
    lower.includes('work_detail') ||
    lower.includes('interaction') ||
    lower.includes('2006') ||
    lower.includes('manager')
  ) {
    domain = 'work_detail';
  } else if (
    lower.includes('tablet') ||
    lower.includes('medicine') ||
    lower.includes('dosage') ||
    lower.includes('frequency') ||
    lower.includes('transcript') ||
    lower.includes('guidance') ||
    lower.includes('clinical') ||
    lower.includes('drug')
  ) {
    domain = 'clinical';
  } else if (
    lower.includes('salesforce') ||
    lower.includes('sf_id') ||
    lower.includes('sync') ||
    lower.includes('crm')
  ) {
    domain = 'sync_audit';
  }

  // Keyword matching runs on the question's wording, which says nothing about
  // which database answered it. If it lands on a group this source cannot
  // serve, fall back to the source's own default rather than offering a
  // question that would jump databases.
  if (allowed && !allowed.includes(domain)) {
    domain = sourceDefault;
  }

  const pool = SUGGESTIONS_BY_DOMAIN[domain] || SUGGESTIONS_BY_DOMAIN.general;
  // Filter out any query that matches the prompt closely
  const filtered = pool.filter(
    item => !lower.includes(item.query.toLowerCase()) && !item.query.toLowerCase().includes(lower)
  );

  // Prefer the de-duplicated list whenever it has anything left. Requiring
  // three survivors meant a small group fell back to the raw pool and
  // re-offered the question the user had just asked. Fewer, useful chips beat
  // four that include a repeat.
  return (filtered.length > 0 ? filtered : pool).slice(0, 4);
}
