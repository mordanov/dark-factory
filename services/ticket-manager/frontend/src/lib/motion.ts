export const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.2 } },
  exit: { opacity: 0, y: -4, transition: { duration: 0.15 } },
};

export const dialogVariants = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, scale: 0.96, transition: { duration: 0.1 } },
};

export const cardHover = {
  whileHover: { y: -2 },
  transition: { duration: 0.15 },
};
