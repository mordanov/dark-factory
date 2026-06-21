import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { pageVariants } from "@/lib/motion";

interface PageTransitionProps {
  children: React.ReactNode;
  className?: string;
}

export function PageTransition({ children, className }: PageTransitionProps) {
  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className={cn("w-full", className)}
    >
      {children}
    </motion.div>
  );
}
