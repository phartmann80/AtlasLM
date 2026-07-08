import React from 'react'
import { redirect } from 'next/navigation'
import { supabaseServer } from '@/lib/supabaseServer'

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const supabase = await supabaseServer()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  return children
}
