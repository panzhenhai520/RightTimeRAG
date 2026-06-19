import { PageContainer } from '@/layouts/components/page-container';
import { Applications } from './applications';
import { Datasets } from './datasets';

const Home = () => {
  return (
    <PageContainer>
      <article>
        <Datasets />
        <Applications />
      </article>
    </PageContainer>
  );
};

export default Home;
