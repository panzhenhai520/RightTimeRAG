import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

type SkeletonCardProps = {
  className?: string;
};
export function SkeletonCard(props: SkeletonCardProps) {
  const { className } = props;
  const skeletonClass =
    'h-8 rounded-lg bg-[rgb(var(--accent-primary)/0.16)] dark:bg-[rgb(var(--accent-primary)/0.22)]';
  return (
    <div className={cn('space-y-4', className)}>
      <Skeleton className={cn(skeletonClass, 'w-full')} />
      <Skeleton className={cn(skeletonClass, 'w-4/5')} />
      <Skeleton className={cn(skeletonClass, 'w-3/5')} />
    </div>
  );
}
