import { render, screen } from '@testing-library/react'
import { axe } from 'jest-axe'
import { describe, expect, it } from 'vitest'
import { Input } from '../../src/components/ui/Input'
import { Textarea } from '../../src/components/ui/Textarea'

describe('Input', () => {
  it('associates the label with the input', () => {
    render(<Input label="Username" />)
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
  })

  it('announces errors via aria-invalid and a linked alert', () => {
    render(<Input label="Password" error="Too short" />)
    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    const error = screen.getByRole('alert')
    expect(error).toHaveTextContent('Too short')
    expect(input).toHaveAttribute('aria-describedby', error.id)
  })

  it('links hint text when there is no error', () => {
    render(<Input label="Email" hint="Never shared" />)
    const input = screen.getByLabelText('Email')
    expect(input).not.toHaveAttribute('aria-invalid')
    expect(input).toHaveAccessibleDescription('Never shared')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Input label="Default" />
        <Input label="With error" error="Required" />
        <Input label="Disabled" disabled />
      </>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('Textarea', () => {
  it('associates the label with the textarea', () => {
    render(<Textarea label="Bio" />)
    expect(screen.getByLabelText('Bio')).toBeInTheDocument()
  })

  it('announces errors via aria-invalid and a linked alert', () => {
    render(<Textarea label="Bio" error="Too long" />)
    const textarea = screen.getByLabelText('Bio')
    expect(textarea).toHaveAttribute('aria-invalid', 'true')
    expect(textarea).toHaveAttribute('aria-describedby', screen.getByRole('alert').id)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Textarea label="Default" />
        <Textarea label="With hint" hint="Max 160 characters" />
        <Textarea label="With error" error="Required" />
      </>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
