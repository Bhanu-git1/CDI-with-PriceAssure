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
  salesforce: [
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

export function getFollowUpSuggestions(userPrompt) {
  if (!userPrompt || typeof userPrompt !== 'string') {
    return SUGGESTIONS_BY_DOMAIN.general.slice(0, 4);
  }

  const lower = userPrompt.toLowerCase();
  let domain = 'general';

  if (
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
    domain = 'salesforce';
  }

  const pool = SUGGESTIONS_BY_DOMAIN[domain] || SUGGESTIONS_BY_DOMAIN.general;
  // Filter out any query that matches the prompt closely
  const filtered = pool.filter(
    item => !lower.includes(item.query.toLowerCase()) && !item.query.toLowerCase().includes(lower)
  );

  return (filtered.length >= 3 ? filtered : pool).slice(0, 4);
}
