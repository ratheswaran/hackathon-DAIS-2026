import { motion } from 'framer-motion';
import { Sparkle } from './sparkle-ticker';

export const Greeting = () => {
  return (
    <div
      key="overview"
      className="mx-auto flex w-full max-w-[720px] flex-col items-center justify-center px-4 pt-20 pb-6"
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        className='flex items-center gap-2.5 text-center font-medium text-[20px] text-fg-1'
      >
        <Sparkle size={30} />
        <span>What would you like me to take on?</span>
      </motion.div>
    </div>
  );
};
