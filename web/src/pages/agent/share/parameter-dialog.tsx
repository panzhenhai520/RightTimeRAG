import { Modal } from '@/components/ui/modal/modal';
import { IModalProps } from '@/interfaces/common';
import DebugContent from '@/pages/agent/debug-content';
import { buildBeginInputListFromObject } from '@/pages/agent/form/begin-form/utils';
import { BeginQuery } from '@/pages/agent/interface';

interface IProps extends IModalProps<any> {
  ok(parameters: any[]): void;
  data: Record<string, Omit<BeginQuery, 'key'>>;
  agentId?: string;
}
export function ParameterDialog({ ok, data, agentId }: IProps) {
  return (
    <Modal
      open
      title={'Parameter'}
      closable={false}
      showfooter={false}
      maskClosable={false}
    >
      <div className="mb-8">
        <DebugContent
          parameters={buildBeginInputListFromObject(data)}
          ok={ok}
          isNext={false}
          btnText={'Submit'}
          agentId={agentId}
        ></DebugContent>
      </div>
    </Modal>
  );
}
