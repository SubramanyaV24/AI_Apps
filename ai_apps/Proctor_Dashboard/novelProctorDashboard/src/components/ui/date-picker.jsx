import * as React from "react"
import { format } from "date-fns"
import { Calendar as CalendarIcon } from "lucide-react"

import { cn } from "./calendar" // Import the utility from calendar (or utils)
import { Button } from "./button" // We have a button component
import { Calendar } from "./calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./popover"

export function DatePicker({ value, onChange, placeholder = "Pick a date" }) {
  const [open, setOpen] = React.useState(false)
  // Convert string "yyyy-MM-dd" to Date object
  const date = value ? new Date(value) : undefined

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={"outline"}
          className={cn(
            "w-full justify-start text-left font-normal bg-white/5 border-white/10 text-foreground hover:bg-white/10",
            !date && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4 opacity-70" />
          {date ? format(date, "PPP") : <span>{placeholder}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0 date-picker-content" align="start">
        <Calendar
          mode="single"
          selected={date}
          onSelect={(newDate) => {
            if (newDate) {
              onChange(format(newDate, "yyyy-MM-dd"))
            } else {
              onChange("")
            }
            setOpen(false) // Automatically close on date select
          }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  )
}
