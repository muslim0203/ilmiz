import { linkHandler } from "@/router";
import { cn } from "@/lib/utils";

/** Ichki havola: robot uchun haqiqiy `<a href>`, foydalanuvchi uchun SPA o'tishi. */
export function AppLink({
  to,
  className,
  onClick,
  children,
  ...rest
}: { to: string } & Omit<React.ComponentProps<"a">, "href">) {
  const navigateOnClick = linkHandler(to);
  return (
    <a
      href={to}
      // Ikkala handler ham chaqiriladi. `<Button asChild>` ichida Radix Slot
      // o'z `onClick` ini uzatadi; ilgari u tarqatishda routerning handlerini
      // bosib ketar va har bosishda sahifa to'liq qayta yuklanardi.
      onClick={(event) => {
        onClick?.(event);
        navigateOnClick(event);
      }}
      className={cn(className)}
      {...rest}
    >
      {children}
    </a>
  );
}
