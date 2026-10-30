type BundleName = 'index-D2QvHT6c.js' | 'corePages-zCQb0dvO.js' | 'donationPages-B8hpj8RV.js'

function replaceOnce(source: string, before: string, after: string, name: BundleName): string {
  if (source.includes(after)) return source
  const occurrences = source.split(before).length - 1
  if (occurrences === 0) {
    throw new Error(`Could not apply the ${name} integration patch; the expected bundle code changed.`)
  }
  if (occurrences !== 1) {
    throw new Error(`Expected one matching integration point in ${name}, found ${occurrences}.`)
  }
  return source.replace(before, after)
}

function replaceAll(source: string, before: string, after: string, name: BundleName): string {
  if (!source.includes(before)) {
    if (source.includes(after)) return source
    throw new Error(`Could not apply the ${name} integration patch; the expected bundle code changed.`)
  }
  return source.split(before).join(after)
}

function restoreDonorScopedDonationLookup(source: string): string {
  const before =
    'ga={list(e=B.id){let t=localStorage.getItem(ma);return(t?JSON.parse(t):la).filter(t=>t.donorId===e)},get(e,t=B.id){return this.list(t).find(t=>t.id===e)},create(e){let t=`don-${Date.now()}`,n={...e,id:t,reference:e.reference??`AF-DEMO-${String(Date.now()).slice(-7)}`,date:new Date().toISOString().slice(0,10),status:`Completed`},r=this.list();return localStorage.setItem(ma,JSON.stringify([n,...r])),n}}'
  const after =
    'ga={list(e=JSON.parse(sessionStorage.getItem("asha-donor-profile")||"null")?.id||B.id){let t=localStorage.getItem(ma);return(t?JSON.parse(t):la).filter(t=>t.donorId===e)},get(e,t=JSON.parse(sessionStorage.getItem("asha-donor-profile")||"null")?.id||B.id){return this.list(t).find(t=>t.id===e)},create(e){let t=`don-${Date.now()}`,n={...e,id:t,reference:e.reference??`AF-DEMO-${String(Date.now()).slice(-7)}`,date:new Date().toISOString().slice(0,10),status:`Completed`},r=this.list();return localStorage.setItem(ma,JSON.stringify([n,...r])),n}}'

  return replaceOnce(source, before, after, 'index-D2QvHT6c.js')
}

function normalizeDonorProfileInitialization(source: string): string {
  const before = /let\[t,n\]=\(0,v\.useState\)\(\(\)=>.*?Sa\(`asha-demo-profile`,B\)\),\[r,i\]=/
  const normalized =
    'let[t,n]=(0,v.useState)(()=>JSON.parse(sessionStorage.getItem("asha-donor-profile")||"null")||Sa(`asha-demo-profile`,B)),[r,i]='
  const match = source.match(before)

  if (!match) {
    if (source.includes(normalized)) return source
    throw new Error('Could not locate the donor profile initializer in the portal bundle.')
  }

  return source.replace(before, normalized)
}

function restoreDonationSimulation(source: string): string {
  const marker = 'onClick:async()=>{if(w)return;T(!0),D(``);try{let token='
  const start = source.indexOf(marker)

  if (start !== -1) {
    const end = source.indexOf(',children:w?`Simulating payment…`', start)
    if (end === -1 || source.indexOf(marker, start + marker.length) !== -1) {
      throw new Error('Could not restore the donation button in the compiled portal bundle.')
    }

    source =
      source.slice(0, start) +
      'onClick:async()=>{if(w)return;T(!0),D(``);let e=await u.simulate(L);if(e.status!==`success`){D(e.message),T(!1);return}let t=a.create({donorId:i.id,causeId:O.causeId,projectId:O.projectId,amount:L,type:O.type,message:O.message,anonymous:O.anonymous});o(`Demo donation completed successfully`),s(`/donate/confirmation/${t.id}`)}' +
      source.slice(end)
  }

  const replacements = [
    ['Make a secure donation using your chosen payment method.', 'A simple, secure-feeling demonstration flow. No real payment is collected.'],
    ['Choose how you would like to pay securely.', 'Choose how you would like to simulate this payment.'],
    ['Credit / debit card', 'Credit / debit card (simulated)'],
    ['Secure online payment', 'Simulation only'],
    ['Payment details are entered securely in Razorpay Checkout and are never stored by this portal.', 'No real payment account, card number, UPI PIN, or banking credential will be requested or stored.'],
    ['Please confirm the details before continuing to secure checkout.', 'Please confirm the details before running the payment simulation.'],
    ['Donation total', 'Demo donation total'],
    ['Your payment will be processed securely by Razorpay. A receipt is issued after the payment is verified.', 'By continuing, you acknowledge this is a prototype simulation. No real transaction or tax-deductible receipt will be created.'],
  ] as const

  for (const [gatewayCopy, demoCopy] of replacements) {
    if (source.includes(gatewayCopy) && !source.includes(demoCopy)) {
      source = replaceOnce(source, gatewayCopy, demoCopy, 'donationPages-B8hpj8RV.js')
    }
  }

  source = source
    .split('Credit / debit card (simulated) (simulated)')
    .join('Credit / debit card (simulated)')

  if (
    !source.includes('u.simulate(L)') ||
    !source.includes('Choose how you would like to simulate this payment.')
  ) {
    throw new Error('Could not verify restoration of the original donation simulation.')
  }

  return source
}

function restoreDemoPaymentService(source: string): string {
  const disabled = '_a={async simulate(){return{status:`failed`,message:`Online checkout is required to process donations.`}}}'
  const simulated =
    '_a={async simulate(e){return await pa(900),e<=0?{status:`failed`,message:`The demo payment could not be processed.`}:{status:`success`,reference:`SIM-${Date.now()}`,message:`Simulated payment completed. No real transaction occurred.`}}}'

  if (source.includes(disabled)) {
    return replaceOnce(source, disabled, simulated, 'index-D2QvHT6c.js')
  }
  if (source.includes(simulated)) return source
  throw new Error('Could not verify the demo payment service in the portal bundle.')
}

function patchDonorLogin(source: string): string {
  const demoLogin =
    'ha={async login(e,t){return await pa(),!e||t.length<6?{success:!1,error:`Enter a valid email and a password of at least 6 characters.`}:(sessionStorage.setItem(`asha-demo-auth`,`true`),{success:!0,data:B})},logout(){sessionStorage.removeItem(`asha-demo-auth`)},isAuthenticated(){return sessionStorage.getItem(`asha-demo-auth`)===`true`}}'
  const apiLogin =
    'ha={async login(e,t){try{let n=await fetch((window.__DONOR_API_BASE_URL__||"http://localhost:8000")+"/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:e,password:t})}),r=await n.json();if(!n.ok)return{success:!1,error:r.detail||"Invalid email or password."};let i={...B,id:r.donor.id,fullName:r.donor.full_name,displayName:r.donor.full_name,email:r.donor.email,phone:r.donor.phone||"",address:r.donor.address||""};sessionStorage.setItem("asha-donor-token",r.access_token);sessionStorage.setItem("asha-donor-profile",JSON.stringify(i));return{success:!0,data:i}}catch{return{success:!1,error:"Unable to reach the donor service. Please try again."}}},logout(){sessionStorage.removeItem("asha-donor-token"),sessionStorage.removeItem("asha-donor-profile")},isAuthenticated(){return Boolean(sessionStorage.getItem("asha-donor-token"))}}'
  const previousApiLogin = apiLogin.replace(
    'fullName:r.donor.full_name,displayName:r.donor.full_name,',
    'fullName:r.donor.full_name,',
  )

  if (source.includes(apiLogin)) return source
  if (source.includes(previousApiLogin)) {
    return replaceOnce(
      source,
      'fullName:r.donor.full_name,email:r.donor.email',
      'fullName:r.donor.full_name,displayName:r.donor.full_name,email:r.donor.email',
      'index-D2QvHT6c.js',
    )
  }
  return replaceOnce(source, demoLogin, apiLogin, 'index-D2QvHT6c.js')
}

export function patchLegacyBundle(name: BundleName, input: string): string {
  let source = input

  if (name === 'donationPages-B8hpj8RV.js') {
    return restoreDonationSimulation(source)
  }

  if (name === 'index-D2QvHT6c.js') {
    source = restoreDemoPaymentService(source)
    source = restoreDonorScopedDonationLookup(source)
    source = normalizeDonorProfileInitialization(source)
    source = patchDonorLogin(source)
    source = replaceOnce(
      source,
      'Sa(`asha-demo-profile`,B)',
      'JSON.parse(sessionStorage.getItem("asha-donor-profile")||"null")||Sa(`asha-demo-profile`,B)',
      name,
    )
    source = replaceOnce(
      source,
      'authenticated:s,setAuthenticated:c,toast:l',
      'authenticated:s,setAuthenticated:e=>{if(e){let r=JSON.parse(sessionStorage.getItem("asha-donor-profile")||"null");r&&n(r)}c(e)},toast:l',
      name,
    )
    source = replaceOnce(
      source,
      'reference:`AF-DEMO-${String(Date.now()).slice(-7)}`',
      'reference:e.reference??`AF-DEMO-${String(Date.now()).slice(-7)}`',
      name,
    )
    source = replaceAll(source, 'Demonstration donor portal', 'Donor portal', name)
  }

  if (name === 'corePages-zCQb0dvO.js') {
    source = replaceOnce(
      source,
      'defaultValues:{email:`ananya@example.com`,password:`donor123`,remember:!0}',
      'defaultValues:{email:``,password:``,remember:!1}',
      name,
    )
    source = replaceOnce(
      source,
      'This prototype uses simulated authentication and payments.',
      'Sign in with the email and password registered for your donor account.',
      name,
    )
    source = replaceOnce(
      source,
      'Use the prefilled demo details to explore the portal.',
      'Enter your donor account credentials to continue.',
      name,
    )
    source = replaceOnce(
      source,
      'password:Il().min(8,`Use at least 8 characters`)',
      'password:Il().min(12,`Use at least 12 characters`)',
      name,
    )
    source = replaceOnce(
      source,
      'hint:`8+ characters, with an uppercase letter and number`',
      'hint:`12+ characters, with an uppercase letter and number`',
      name,
    )
    source = replaceOnce(source, 'Demo account created', 'Account created', name)
    source = replaceOnce(
      source,
      'Your registration has been recorded for this prototype. No welcome email was sent.',
      'Your donor account has been created. You can now sign in with your email and password.',
      name,
    )
    source = replaceOnce(
      source,
      'function Zu(){let[e,n]=(0,D.useState)(!1),{register:r,handleSubmit:i,formState:{errors:a,isSubmitting:o}}=jt({resolver:Vt(Xu)})',
      'function Zu(){let[e,n]=(0,D.useState)(!1),[registrationError,setRegistrationError]=(0,D.useState)(``),{register:r,handleSubmit:i,formState:{errors:a,isSubmitting:o}}=jt({resolver:Vt(Xu)})',
      name,
    )
    source = replaceOnce(
      source,
      'onSubmit:i(async()=>{await new Promise(e=>setTimeout(e,500)),n(!0)})',
      'onSubmit:i(async e=>{try{let r=await fetch((window.__DONOR_API_BASE_URL__||"http://localhost:8000")+"/api/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({full_name:e.fullName,email:e.email,password:e.password,phone:e.phone})}),t=await r.json();if(!r.ok)throw Error(t.detail||"Account creation failed.");n(!0)}catch(e){setRegistrationError(e instanceof Error?e.message:"Account creation failed.")}})',
      name,
    )
    source = replaceOnce(
      source,
      'a.terms&&(0,$.jsx)(`span`,{className:`error-text full`,children:a.terms.message}),(0,$.jsx)(`div`,{className:`full`',
      'a.terms&&(0,$.jsx)(`span`,{className:`error-text full`,children:a.terms.message}),registrationError&&(0,$.jsx)(`p`,{className:`alert error full`,children:registrationError}),(0,$.jsx)(`div`,{className:`full`',
      name,
    )
  }

  return source
}
