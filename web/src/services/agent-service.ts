import {
  IAgentActiveRunsResponse,
  IAgentLogsRequest,
  IAgentRunArtifactsResponse,
  IAgentRunEventsResponse,
  IAgentRunState,
  IAgentRunTraceResponse,
  IAgentValidationResponse,
  IAgentOperatorSchemaResponse,
  IPipeLineListRequest,
} from '@/interfaces/database/agent';
import { IAgentWebhookTraceRequest } from '@/interfaces/request/agent';
import api from '@/utils/api';
import { registerNextServer } from '@/utils/register-server';
import request from '@/utils/request';

const {
  createAgent,
  updateAgent: updateAgentApi,
  listAgents,
  deleteAgent,
  agentChatCompletion,
  resetAgent,
  listAgentTemplate,
  listAgentOperatorSchema,
  testDbConnect,
  getInputElements,
  trace,
  fetchVersionList,
  fetchVersion,
  getAgent,
  validateAgent,
  fetchAgentSessions,
  fetchExternalAgentInputs,
  prompt,
  cancelDataflow,
  cancelCanvas,
  agentRun,
  agentRunEvents,
  agentRunArtifacts,
  agentRunTrace,
  createAgentRun,
  listAgentRuns,
  cancelAgentRun,
} = api;

const methods = {
  getAgent: {
    url: getAgent,
    method: 'get',
  },
  createAgent: {
    url: createAgent,
    method: 'post',
  },
  fetchVersionList: {
    url: fetchVersionList,
    method: 'get',
  },
  fetchVersion: {
    url: (config: { agentId: string; versionId: string }) =>
      fetchVersion(config.agentId, config.versionId),
    method: 'get',
  },
  listAgents: {
    url: listAgents,
    method: 'get',
  },
  listAgentTags: {
    url: api.listAgentTags,
    method: 'get',
  },
  resetAgent: {
    url: resetAgent,
    method: 'post',
  },
  deleteAgent: {
    url: deleteAgent,
    method: 'delete',
  },
  agentChatCompletion: {
    url: agentChatCompletion,
    method: 'post',
  },
  listAgentTemplate: {
    url: listAgentTemplate,
    method: 'get',
  },
  listAgentOperatorSchema: {
    url: listAgentOperatorSchema,
    method: 'get',
  },
  testDbConnect: {
    url: testDbConnect,
    method: 'post',
  },
  getInputElements: {
    url: getInputElements,
    method: 'get',
  },
  debugSingle: {
    url: (config: { agentId: string; componentId: string }) =>
      api.debug(config.agentId, config.componentId),
    method: 'post',
  },
  uploadAgentFile: {
    url: (config: { agentId: string }) => api.uploadAgentFile(config.agentId),
    method: 'post',
  },
  trace: {
    url: (config: { agentId: string; messageId: string }) =>
      trace(config.agentId, config.messageId),
    method: 'get',
  },
  inputForm: {
    url: (config: { agentId: string; componentId: string }) =>
      api.inputForm(config.agentId, config.componentId),
    method: 'get',
  },
  validateAgent: {
    url: validateAgent,
    method: 'post',
  },
  fetchAgentLogs: {
    url: fetchAgentSessions,
    method: 'get',
  },
  fetchExternalAgentInputs: {
    url: fetchExternalAgentInputs,
    method: 'get',
  },
  fetchPrompt: {
    url: prompt,
    method: 'get',
  },
  cancelDataflow: {
    url: cancelDataflow,
    method: 'post',
  },
  cancelCanvas: {
    url: cancelCanvas,
    method: 'post',
  },
  fetchAgentRun: {
    url: agentRun,
    method: 'get',
  },
  createAgentRun: {
    url: (config: { agentId: string }) => createAgentRun(config.agentId),
    method: 'post',
  },
  listAgentRuns: {
    url: (config: { agentId: string }) => listAgentRuns(config.agentId),
    method: 'get',
  },
  fetchAgentRunEvents: {
    url: agentRunEvents,
    method: 'get',
  },
  fetchAgentRunArtifacts: {
    url: agentRunArtifacts,
    method: 'get',
  },
  fetchAgentRunTrace: {
    url: agentRunTrace,
    method: 'get',
  },
  cancelAgentRun: {
    url: cancelAgentRun,
    method: 'post',
  },
  createAgentSession: {
    url: api.createAgentSession,
    method: 'post',
  },
} as const;

const agentService = registerNextServer<keyof typeof methods>(methods);

export const updateAgent = (
  agentId: string,
  params: {
    title?: string;
    dsl?: Record<string, any>;
    avatar?: string;
    description?: string | null;
    permission?: string;
    release?: string;
  },
) => {
  return request(updateAgentApi(agentId), { method: 'put', data: params });
};

export const updateAgentTags = (agentId: string, tags: string[]) => {
  return request(api.updateAgentTags(agentId), {
    method: 'put',
    data: { tags: tags.join(',') },
  });
};

export const fetchAgentRun = (runId: string) => {
  return request<{ data: IAgentRunState }>(api.agentRun(runId), {
    method: 'get',
  });
};

export const createBackgroundAgentRun = (
  agentId: string,
  data: Record<string, any>,
) => {
  return request<{
    data: {
      run_id: string;
      session_id: string;
      message_id: string;
      task_id: string;
      status: IAgentRunState['status'];
    };
  }>(api.createAgentRun(agentId), {
    method: 'post',
    data,
  });
};

export const listAgentActiveRuns = (agentId: string, sessionId?: string) => {
  return request<{ data: IAgentActiveRunsResponse }>(
    api.listAgentRuns(agentId),
    {
      method: 'get',
      params: sessionId ? { session_id: sessionId } : undefined,
    },
  );
};

export const fetchAgentRunEvents = (runId: string, after = -1) => {
  return request<{ data: IAgentRunEventsResponse }>(api.agentRunEvents(runId), {
    method: 'get',
    params: { after },
  });
};

export const fetchAgentRunArtifacts = (runId: string) => {
  return request<{ data: IAgentRunArtifactsResponse }>(
    api.agentRunArtifacts(runId),
    {
      method: 'get',
    },
  );
};

export const fetchAgentRunTrace = (runId: string) => {
  return request<{ data: IAgentRunTraceResponse }>(api.agentRunTrace(runId), {
    method: 'get',
  });
};

export const cancelAgentRunById = (runId: string) => {
  return request<{ data: { canceled: boolean } }>(api.cancelAgentRun(runId), {
    method: 'post',
  });
};

export const validateAgentDsl = (
  agentId: string,
  dsl?: Record<string, any>,
) => {
  return request<{ data: IAgentValidationResponse }>(
    api.validateAgent(agentId),
    {
      method: dsl ? 'post' : 'get',
      data: dsl ? { dsl } : undefined,
    },
  );
};

export const fetchAgentOperatorSchema = () => {
  return request<{ data: IAgentOperatorSchemaResponse }>(
    api.listAgentOperatorSchema,
    {
      method: 'get',
    },
  );
};

export const fetchAgentFileParserHealth = (params?: {
  layout_recognize?: string;
  deep?: boolean;
}) => {
  return request<{ data: Record<string, any> }>(api.agentFileParserHealth, {
    method: 'get',
    params,
  });
};

export const fetchTrace = (data: { canvas_id: string; message_id: string }) => {
  return request.get(
    methods.trace.url({
      agentId: data.canvas_id,
      messageId: data.message_id,
    }),
  );
};
export const fetchAgentLogsByCanvasId = (
  canvasId: string,
  params: IAgentLogsRequest,
) => {
  return request.get(methods.fetchAgentLogs.url(canvasId), { params: params });
};

export const fetchAgentLogsById = (canvasId: string, sessionId: string) => {
  return request.get(api.fetchAgentSessionById(canvasId, sessionId));
};

export const fetchPipeLineList = (params: IPipeLineListRequest) => {
  return request.get(api.listAgents, { params: params });
};

export const fetchWebhookTrace = (
  id: string,
  params: IAgentWebhookTraceRequest,
) => {
  return request.get(api.fetchWebhookTrace(id), { params: params });
};

export function createAgentSession({ id, name }: { id: string; name: string }) {
  return request.post(api.createAgentSession(id), { data: { name } });
}

export const deleteAgentSession = (canvasId: string, sessionId: string) => {
  return request.delete(api.fetchAgentSessionById(canvasId, sessionId));
};

export const uploadAgentFile = (agentId: string, data: FormData) => {
  return request(api.uploadAgentFile(agentId), {
    method: 'post',
    data,
  });
};

export default agentService;
